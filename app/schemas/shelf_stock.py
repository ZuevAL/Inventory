from pydantic import BaseModel


class SchemaShelfStock(BaseModel):
    product_barcode: str
    shelf_code: str
    quantity: int