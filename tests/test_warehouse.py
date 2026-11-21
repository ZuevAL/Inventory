import sqlite3
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from uuid import uuid4

import pytest

from app.cli.import_orders import import_orders
from app.models.product import Product
from app.models.shelf import Shelf
from app.models.shelf_stock import ShelfStock
from tests.conftest import TEST_PASSWORD
from tests.test_migrations import migrate

WAREHOUSE = "/api/v1/warehouse"
PRODUCT_BARCODE = "4601234567893"
OTHER_BARCODE = "4601234567909"
ORDERS_CSV = (
    "order_number,customer,product_barcode,quantity\n"
    f"1042,Магазин,{PRODUCT_BARCODE},5\n"
    f"1042,Магазин,{OTHER_BARCODE},2\n"
    f"1043,Магазин,{PRODUCT_BARCODE},4\n"
)


@pytest.fixture
def warehouse(auth_env):
    user_id = auth_env.create_user()
    response = auth_env.client.post("/api/v1/auth/login", json={
        "login": "worker_01", "password": TEST_PASSWORD,
    })
    assert response.status_code == 200, response.text
    auth_env.client.headers["Authorization"] = "Bearer " + response.json()["access_token"]

    async def seed(db):
        product = Product(name="Кабель USB-C", barcode=PRODUCT_BARCODE)
        adapter = Product(name="Адаптер питания", barcode=OTHER_BARCODE)
        first = Shelf(code="A-01-01")
        second = Shelf(code="A-01-02")
        empty = Shelf(code="B-02-01")
        db.add_all([product, adapter, first, second, empty])
        await db.flush()
        db.add_all([
            ShelfStock(product_id=product.id, shelf_id=first.id, quantity=4),
            ShelfStock(product_id=product.id, shelf_id=second.id, quantity=1),
            ShelfStock(product_id=adapter.id, shelf_id=first.id, quantity=2),
        ])
        await db.commit()
        await import_orders(db, StringIO(ORDERS_CSV))

    auth_env.database(seed)
    return auth_env.client, user_id


def snapshot(client):
    response = client.get(f"{WAREHOUSE}/snapshot")
    assert response.status_code == 200, response.text
    return response.json()


def product_id(state, barcode=PRODUCT_BARCODE):
    return next(product["id"] for product in state["products"] if barcode in product["barcodes"])


def shelf(state, code):
    return next(shelf for shelf in state["shelves"] if shelf["code"] == code)


def order_line(state, order_number="1042", barcode=PRODUCT_BARCODE):
    order = next(order for order in state["orders"] if order["number"] == order_number)
    return next(line for line in order["lines"] if line["product_id"] == product_id(state, barcode))


def quantity(state, shelf_id, product):
    return next((row["quantity"] for row in state["stock"]
                 if row["shelf_id"] == shelf_id and row["product_id"] == product), 0)


def operation(kind, shelf_code, quantity=1, *, product_code=PRODUCT_BARCODE, order_line_id=None):
    data = {
        "operation_id": str(uuid4()), "kind": kind, "product_code": product_code,
        "shelf_code": shelf_code, "quantity": quantity,
    }
    if order_line_id is not None:
        data["order_line_id"] = order_line_id
    return data


def post_operation(client, payload):
    return client.post(f"{WAREHOUSE}/operations", json=payload)


def test_warehouse_endpoints_require_authentication(auth_env):
    assert auth_env.client.get(f"{WAREHOUSE}/snapshot").status_code == 401
    assert post_operation(auth_env.client, operation("putaway", "A-01-01")).status_code == 401


def test_putaway_creates_stock_and_retries_exactly_once(warehouse):
    client, user_id = warehouse
    before = snapshot(client)
    code = shelf(before, "B-02-01")
    payload = operation("putaway", code["qr"], 3)
    first = post_operation(client, payload)
    replay = post_operation(client, payload)
    assert first.is_success, first.text
    assert replay.is_success, replay.text
    assert replay.json() == first.json()
    conflict = post_operation(client, {**payload, "quantity": 4})
    assert conflict.status_code == 409, conflict.text

    after = snapshot(client)
    assert quantity(after, code["id"], product_id(before)) == 3
    stock_rows = client.get("/api/v1/stock/", params={"limit": 500}).json()
    rows_for_shelf = [row for row in stock_rows if row["shelf_code"] == code["code"]]
    assert len(rows_for_shelf) == 1
    assert rows_for_shelf[0]["product_barcode"] == PRODUCT_BARCODE
    assert rows_for_shelf[0]["quantity"] == 3
    assert len(after["operations"]) == 1
    audit = after["operations"][0]
    assert audit["operation_id"] == payload["operation_id"]
    assert audit["user_id"] == user_id
    assert audit["kind"] == "putaway"
    assert audit["shelf_id"] == code["id"]
    assert audit["product_id"] == product_id(before)
    assert audit["quantity"] == 3


def test_putaway_adds_to_existing_stock(warehouse):
    client, _ = warehouse
    before = snapshot(client)
    selected = shelf(before, "A-01-01")
    response = post_operation(client, operation("putaway", selected["code"], 3))
    assert response.is_success, response.text
    assert quantity(snapshot(client), selected["id"], product_id(before)) == 7


def test_shelf_qr_selects_original_shelf_when_a_display_code_matches_it(warehouse):
    client, _ = warehouse
    before = snapshot(client)
    original = shelf(before, "A-01-01")
    created = client.post("/api/v1/shelves/", json={"code": original["qr"]})
    assert created.is_success, created.text
    collision = created.json()["id"]

    response = post_operation(client, operation("putaway", original["qr"], 2))
    assert response.is_success, response.text
    assert response.json()["shelf_id"] == original["id"]
    after = snapshot(client)
    assert quantity(after, original["id"], product_id(before)) == 6
    assert quantity(after, collision, product_id(before)) == 0


def test_pick_uses_scanned_shelf_updates_order_and_does_not_double_apply(warehouse):
    client, user_id = warehouse
    before = snapshot(client)
    first = shelf(before, "A-01-01")
    second = shelf(before, "A-01-02")
    line = order_line(before)
    pick_first = operation("pick", first["qr"], 4, order_line_id=line["id"])
    pick_second = operation("pick", second["qr"], order_line_id=line["id"])
    for payload in (pick_first, pick_second, pick_second):
        response = post_operation(client, payload)
        assert response.is_success, response.text

    after = snapshot(client)
    assert order_line(after)["picked"] == line["quantity"] == 5
    assert order_line(after, "1043")["picked"] == 0
    assert quantity(after, first["id"], product_id(before)) == 0
    assert quantity(after, second["id"], product_id(before)) == 0
    assert quantity(after, first["id"], product_id(before, OTHER_BARCODE)) == 2
    assert {row["operation_id"] for row in after["operations"]} == {
        pick_first["operation_id"], pick_second["operation_id"],
    }
    assert len(after["operations"]) == 2
    assert {row["order_line_id"] for row in after["operations"]} == {line["id"]}
    assert {row["user_id"] for row in after["operations"]} == {user_id}


@pytest.mark.parametrize(("overrides", "status"), [
    ({"product_code": "unknown"}, 404),
    ({"shelf_code": "unknown"}, 404),
    ({"product_code": OTHER_BARCODE}, 409),
    ({"shelf_code": "B-02-01"}, 409),
    ({"shelf_code": "A-01-02", "quantity": 2}, 409),
    ({"quantity": 0}, 422),
    ({"order_line_id": None}, 422),
])
def test_pick_validation_leaves_stock_order_and_audit_unchanged(warehouse, overrides, status):
    client, _ = warehouse
    before = snapshot(client)
    payload = operation("pick", "A-01-01", order_line_id=order_line(before)["id"])
    response = post_operation(client, {**payload, **overrides})
    assert response.status_code == status, response.text
    assert snapshot(client) == before


def test_pick_rejects_overpicking_even_when_shelf_has_stock(warehouse):
    client, _ = warehouse
    line = order_line(snapshot(client))
    first_pick = post_operation(client, operation("pick", "A-01-01", 3, order_line_id=line["id"]))
    reserve = post_operation(client, operation("putaway", "A-01-01", 5))
    assert first_pick.is_success, first_pick.text
    assert reserve.is_success, reserve.text
    before = snapshot(client)
    response = post_operation(client, operation("pick", "A-01-01", 3, order_line_id=line["id"]))
    assert response.status_code == 409, response.text
    assert snapshot(client) == before


def test_two_concurrent_orders_cannot_overdraw_the_same_stock(warehouse):
    client, _ = warehouse
    before = snapshot(client)
    first = shelf(before, "A-01-01")
    candidates = [
        operation("pick", first["qr"], 4, order_line_id=order_line(before, number)["id"])
        for number in ("1042", "1043")
    ]
    barrier = Barrier(2, timeout=5)

    def pick(payload):
        barrier.wait()
        return post_operation(client, payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(pick, candidates))
    assert sum(response.is_success for response in responses) == 1, [response.text for response in responses]
    assert [response.status_code for response in responses if not response.is_success] == [409]

    after = snapshot(client)
    assert quantity(after, first["id"], product_id(before)) == 0
    assert sorted(order_line(after, number)["picked"] for number in ("1042", "1043")) == [0, 4]
    assert len(after["operations"]) == 1


def test_manual_adjustment_and_mobile_pick_share_the_same_stock_limit(warehouse):
    client, _ = warehouse
    before = snapshot(client)
    selected = shelf(before, "A-01-01")
    pick = operation("pick", selected["qr"], 4, order_line_id=order_line(before)["id"])
    barrier = Barrier(2, timeout=5)

    def manual_adjustment():
        barrier.wait()
        return client.patch("/api/v1/stock/", params={
            "barcode": PRODUCT_BARCODE, "shelf_code": selected["code"], "adding": -4,
        })

    def mobile_pick():
        barrier.wait()
        return post_operation(client, pick)

    with ThreadPoolExecutor(max_workers=2) as pool:
        manual = pool.submit(manual_adjustment)
        mobile = pool.submit(mobile_pick)
        responses = [manual.result(), mobile.result()]
    assert sorted(response.status_code for response in responses) == [200, 409]

    after = snapshot(client)
    assert quantity(after, selected["id"], product_id(before)) == 0
    assert order_line(after)["picked"] == (4 if responses[1].is_success else 0)
    assert len(after["operations"]) == int(responses[1].is_success)


@pytest.mark.parametrize("csv_text", [
    ORDERS_CSV,
    (
        "order_number,customer,product_barcode,quantity\n"
        f"1044,Магазин,{PRODUCT_BARCODE},1\n"
        "1045,Магазин,unknown,2\n"
    ),
])
def test_order_import_rejects_invalid_batch_without_partial_writes(warehouse, auth_env, csv_text):
    client, _ = warehouse
    before = snapshot(client)

    async def import_file(db):
        await import_orders(db, StringIO(csv_text))

    with pytest.raises(ValueError):
        auth_env.database(import_file)
    assert snapshot(client) == before


def test_warehouse_migration_preserves_preexisting_stock(tmp_path):
    database_path = tmp_path / "warehouse-migration.db"
    migrate(database_path, "d94281e6ac03")
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO products (id, name, barcode) VALUES (3, 'Кабель', '123')")
        connection.execute("INSERT INTO shelves (id, code) VALUES (7, 'A-01-01')")
        connection.execute("INSERT INTO shelf_stock (product_id, shelf_id, quantity) VALUES (3, 7, 12)")

    migrate(database_path, "head")
    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"warehouse_orders", "warehouse_order_lines", "warehouse_operations"} <= tables
        assert connection.execute("SELECT product_id, shelf_id, quantity FROM shelf_stock").fetchall() == [(3, 7, 12)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
