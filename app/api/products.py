from fastapi import APIRouter, HTTPException

from app.db.models import Product

router = APIRouter()


def _session_local():
    from app.main import SessionLocal

    return SessionLocal


@router.get("/products/{sku}/stock")
def read_stock(sku: str):
    with _session_local()() as session:
        product = session.get(Product, sku)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"sku": product.sku, "stock": product.stock}
