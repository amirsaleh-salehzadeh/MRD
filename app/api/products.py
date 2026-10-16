from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Product
from app.schemas import ProductCreate

router = APIRouter()


def _session_local():
    from app.main import SessionLocal

    return SessionLocal


@router.get("/api/v1/products/{sku}/stock")
def read_stock(sku: str):
    with _session_local()() as session:
        product = session.get(Product, sku)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"sku": product.sku, "stock": product.stock}


@router.get("/api/v1/products")
def list_products():
    with _session_local()() as session:
        products = session.scalars(select(Product).order_by(Product.sku)).all()
        return [
            {
                "sku": product.sku,
                "name": product.name,
                "price_cents": product.price_cents,
                "stock": product.stock,
            }
            for product in products
        ]


@router.get("/api/v1/products/{sku}")
def read_product(sku: str):
    with _session_local()() as session:
        product = session.get(Product, sku)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return {
            "sku": product.sku,
            "name": product.name,
            "price_cents": product.price_cents,
            "stock": product.stock,
        }


@router.post("/api/v1/products", status_code=201)
def create_product(request: ProductCreate):
    with _session_local().begin() as session:
        inserted = session.execute(
            insert(Product)
            .values(
                sku=request.sku,
                name=request.name,
                price_cents=request.price_cents,
                stock=request.stock,
            )
            .on_conflict_do_nothing(index_elements=[Product.sku])
            .returning(Product.sku)
        ).scalar_one_or_none()
        if inserted is None:
            raise HTTPException(status_code=409, detail="Product SKU already exists")
    return {
        "sku": request.sku,
        "name": request.name,
        "price_cents": request.price_cents,
        "stock": request.stock,
    }
