from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from app.database import get_db
from app.schemas.province import ProvinceSummary

router = APIRouter(prefix="/provinces", tags=["Provinces"])

SQL = text("""
WITH exploded AS (
    SELECT
        p.province_id,
        p.province_name,
        COALESCE(d.population, 0) AS population,
        mi.elem::text AS industry
    FROM provinces p
    LEFT JOIN districts d
        ON d.province_id = p.province_id
    LEFT JOIN LATERAL jsonb_array_elements(d.major_industries) AS mi(elem)
        ON TRUE
),
population_sum AS (
    SELECT
        p.province_id,
        p.province_name,
        COALESCE(SUM(d.population), 0) AS population_total
    FROM provinces p
    LEFT JOIN districts d ON d.province_id = p.province_id
    GROUP BY p.province_id, p.province_name
)
SELECT
    ps.province_id,
    ps.province_name,
    ps.population_total,
    COALESCE(
        (
            SELECT jsonb_agg(DISTINCT e.industry ORDER BY e.industry)
            FROM exploded e
            WHERE e.province_id = ps.province_id
              AND e.industry IS NOT NULL
        ),
        '[]'::jsonb
    ) AS industries_json
FROM population_sum ps
ORDER BY ps.province_id;
""")

@router.get("/summary", response_model=List[ProvinceSummary])
def provinces_summary(db: Session = Depends(get_db)):
    rows = db.execute(SQL).mappings().all()
    results: List[ProvinceSummary] = []
    for r in rows:
        industries = list(r["industries_json"] or [])
        results.append(
            ProvinceSummary(
                province_id=r["province_id"],
                province_name=r["province_name"],
                population_total=int(r["population_total"] or 0),
                major_industries=industries,
            )
        )
    return results