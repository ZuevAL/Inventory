from pydantic import BaseModel


class SchemaShelfStock(BaseModel):
    product_id: int
    shelf_id: int
    quantity: int