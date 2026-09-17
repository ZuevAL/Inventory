from sqlalchemy import Column, Integer, String
from app.models.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    barcode = Column(String, unique=True, nullable=False)