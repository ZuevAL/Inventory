from pydantic import BaseModel

class SchemaProduct(BaseModel):
    name: str
    barcode: str

