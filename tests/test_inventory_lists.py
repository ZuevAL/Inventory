import pytest

from app.models.product import Product
from app.models.shelf import Shelf
from app.models.shelf_stock import ShelfStock
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def inventory_client(auth_env):
    auth_env.create_user()
    response = auth_env.client.post("/api/v1/auth/login", json={
        "login": "worker_01", "password": TEST_PASSWORD,
    })
    assert response.status_code == 200
    auth_env.client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    return auth_env.client


@pytest.fixture
def populated_inventory(auth_env, inventory_client):
    async def seed(db):
        products = [Product(name=f"Товар {i}", barcode=f"000{i}") for i in range(7)]
        shelves = [Shelf(code=f"A-{i}") for i in range(7)]
        db.add_all(products + shelves)
        await db.flush()
        db.add_all([
            ShelfStock(product_id=product.id, shelf_id=shelf.id, quantity=i)
            for i, (product, shelf) in enumerate(zip(products, shelves))
        ])
    auth_env.database(seed)
    return inventory_client


@pytest.mark.parametrize("resource", ["products", "shelves", "stock"])
def test_inventory_lists_default_to_five_and_allow_loading_all(populated_inventory, resource):
    path = f"/api/v1/{resource}/"
    preview = populated_inventory.get(path)
    assert preview.status_code == 200
    assert [item["id"] for item in preview.json()] == [1, 2, 3, 4, 5]

    remainder = populated_inventory.get(path, params={"offset": 5, "limit": 100})
    assert remainder.status_code == 200
    assert [item["id"] for item in remainder.json()] == [6, 7]

    full = populated_inventory.get(path, params={"limit": 100})
    assert len(full.json()) == 7
    assert full.json() == preview.json() + remainder.json()
    assert populated_inventory.get(path, params={"offset": 7}).json() == []


def test_stock_includes_names_codes_and_existing_foreign_keys(populated_inventory):
    response = populated_inventory.get("/api/v1/stock/", params={"offset": 6})
    assert response.status_code == 200
    assert response.json() == [{
        "id": 7, "product_id": 7, "shelf_id": 7,
        "product_name": "Товар 6", "product_barcode": "0006",
        "shelf_code": "A-6", "quantity": 6,
    }]
    assert populated_inventory.get("/api/v1/stock/").json()[0]["quantity"] == 0


@pytest.mark.parametrize("resource", ["products", "shelves", "stock"])
@pytest.mark.parametrize("params", [
    {"offset": -1}, {"limit": 0}, {"limit": 501}, {"offset": "invalid"},
])
def test_inventory_pagination_validates_bounds(inventory_client, resource, params):
    assert inventory_client.get(f"/api/v1/{resource}/", params=params).status_code == 422


@pytest.mark.parametrize("resource", ["products", "shelves", "stock"])
def test_empty_inventory_lists(inventory_client, resource):
    response = inventory_client.get(f"/api/v1/{resource}/")
    assert response.status_code == 200
    assert response.json() == []
