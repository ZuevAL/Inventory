from pydantic import BaseModel


class QuantityChange(BaseModel):
    change: int