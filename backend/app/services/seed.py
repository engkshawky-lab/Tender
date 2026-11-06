"""Base data loaded on first start: cost-code tree (building + infra), admin user, starter resource library,
rate-analysis templates and a few suppliers. Prices are illustrative placeholders — replace with current prices."""
import os
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..models import BuildUpTemplate, CostCode, Resource, Supplier, User
from .defaults import COST_CODES


def seed_cost_codes(db: Session):
    if db.scalar(select(CostCode.id).limit(1)):
        return
    for code, ar, en, ptype, children in COST_CODES:
        div = CostCode(code=code, name_ar=ar, name_en=en, level=1, project_type=ptype)
        db.add(div)
        db.flush()
        for ccode, car, cen, unit, kw in children:
            # level 2 = work type; level 3 = standard item (same text, used for coding)
            wt = CostCode(code=ccode, name_ar=car, name_en=cen, level=2, parent_id=div.id, project_type=ptype, unit=unit)
            db.add(wt)
            db.flush()
            db.add(CostCode(code=f"{ccode}.001", name_ar=car, name_en=cen, level=3, parent_id=wt.id, project_type=ptype,
                            unit=unit, keywords=kw))


def seed_admin(db: Session):
    if db.scalar(select(User.id).limit(1)):
        return
    db.add(User(username="admin", full_name="مدير النظام", roles=["admin"],
                password_hash=hash_password(os.getenv("TP_ADMIN_PASSWORD", "admin123"))))


RESOURCES = [
    # code, name, kind, unit, price, currency, age_days, productivity, waste
    ("M-CON-350", "خرسانة جاهزة 350 كجم/م3", "material", "m3", 3200, "EGP", 20, None, 2.5),
    ("M-CON-250", "خرسانة جاهزة عادية 250 كجم/م3", "material", "m3", 2700, "EGP", 20, None, 2.5),
    ("M-STL", "حديد تسليح", "material", "ton", 39000, "EGP", 15, None, 5),
    ("M-FRM", "شدات خشبية (استهلاك للمتر المكعب)", "material", "m3", 450, "EGP", 30, None, 0),
    ("M-BLK", "طوب أسمنتي مصمت 25 سم", "material", "m2", 210, "EGP", 40, None, 5),
    ("M-MRT", "مونة أسمنتية", "material", "m3", 1900, "EGP", 40, None, 5),
    ("M-PLS", "مواد بياض (للمتر المربع)", "material", "m2", 65, "EGP", 120, None, 5),
    ("M-PNT", "دهان بلاستيك (للمتر المربع 3 أوجه)", "material", "m2", 70, "EGP", 30, None, 5),
    ("M-SND", "رمل ردم نظيف", "material", "m3", 220, "EGP", 30, None, 10),
    ("M-POR-IMP", "بورسلين مستورد 60×60", "material", "m2", 14, "USD", 25, None, 7),
    ("L-CARP", "نجار مسلح + مساعد (يومية)", "labor", "day", 1400, "EGP", 30, None, None),
    ("L-MASON", "بناء + مساعد (يومية)", "labor", "day", 1200, "EGP", 30, None, None),
    ("L-PLAST", "مبيض محارة + مساعد (يومية)", "labor", "day", 1200, "EGP", 30, None, None),
    ("L-GEN", "عامل عادي (يومية)", "labor", "day", 450, "EGP", 30, None, None),
    ("E-EXC", "حفار (ساعة)", "equipment", "hr", 1500, "EGP", 30, None, None),
    ("E-LOAD", "لودر + قلاب نقل (ساعة)", "equipment", "hr", 1300, "EGP", 30, None, None),
    ("E-PUMP", "مضخة خرسانة (م3)", "equipment", "m3", 120, "EGP", 30, None, None),
    ("E-ROLL", "هراس (ساعة)", "equipment", "hr", 900, "EGP", 30, None, None),
    ("M-AGG", "سن كسر / أساس مساعد", "material", "m3", 480, "EGP", 30, None, 3),
    ("M-ASPH", "خلطة أسفلتية (طن)", "material", "ton", 2900, "EGP", 30, None, 3),
    ("M-HDPE200", "ماسورة HDPE PE100 قطر 200 مم", "material", "m", 1350, "EGP", 30, None, 2),
    ("M-UPVC315", "ماسورة uPVC صرف قطر 315 مم", "material", "m", 1150, "EGP", 30, None, 2),
]

TEMPLATES = [
    ("خرسانة مسلحة أسقف (م3)", "m3", "B03.04.001", [
        ("M-CON-350", 1.0, "supply"), ("M-STL", 0.11, "supply"), ("M-FRM", 1.0, "supply"),
        ("L-CARP", 0.35, "apply"), ("E-PUMP", 1.0, "apply")]),
    ("خرسانة مسلحة قواعد (م3)", "m3", "B03.02.001", [
        ("M-CON-350", 1.0, "supply"), ("M-STL", 0.09, "supply"), ("M-FRM", 0.6, "supply"),
        ("L-CARP", 0.25, "apply"), ("E-PUMP", 1.0, "apply")]),
    ("خرسانة عادية (م3)", "m3", "B03.01.001", [("M-CON-250", 1.0, "supply"), ("L-GEN", 0.3, "apply")]),
    ("مباني طوب 25 سم (م2)", "m2", "B04.01.001", [("M-BLK", 1.0, "supply"), ("M-MRT", 0.03, "supply"), ("L-MASON", 0.08, "apply")]),
    ("بياض داخلي (م2)", "m2", "B06.01.001", [("M-PLS", 1.0, "supply"), ("L-PLAST", 0.05, "apply")]),
    ("حفر بالمعدات (م3)", "m3", "B02.01.001", [("E-EXC", 0.02, "apply"), ("E-LOAD", 0.025, "apply")]),
    ("ردم رمل (م3)", "m3", "B02.02.001", [("M-SND", 1.15, "supply"), ("E-ROLL", 0.02, "apply"), ("L-GEN", 0.1, "apply")]),
]

SUPPLIERS = [
    ("الشركة المتحدة للتكييف", "subcontractor", ["HVAC"], 4, "Carrier"),
    ("النور للمقاولات الكهربائية", "subcontractor", ["Electrical"], 3.5, ""),
    ("مصنع الدلتا للأثاث", "supplier", ["Furniture"], 4, ""),
    ("سيراميكا الشرق", "supplier", ["Finishes"], 3, ""),
    ("فريق التشطيبات الحديثة", "subcontractor", ["Finishes"], 3.5, ""),
    ("الهندسية للبنية التحتية", "subcontractor", ["Roads", "Networks"], 4, ""),
]


def seed_library(db: Session):
    if db.scalar(select(Resource.id).limit(1)):
        return
    by_code = {}
    for code, name, kind, unit, price, cur, age, prod, waste in RESOURCES:
        r = Resource(code=code, name=name, kind=kind, unit=unit, price=price, currency=cur,
                     price_date=date.today() - timedelta(days=age), source="قائمة أسعار مبدئية", productivity=prod, waste_pct=waste)
        db.add(r)
        by_code[code] = r
    db.flush()
    codes = {c.code: c.id for c in db.scalars(select(CostCode)).all()}
    for name, unit, cc, lines in TEMPLATES:
        db.add(BuildUpTemplate(name=name, unit=unit, cost_code_id=codes.get(cc), lines=[
            {"resource_id": by_code[rc].id, "kind": by_code[rc].kind, "part": part, "coefficient": coef,
             "description": by_code[rc].name, "waste_pct": float(by_code[rc].waste_pct or 0)} for rc, coef, part in lines]))
    for name, kind, trades, rating, approved in SUPPLIERS:
        db.add(Supplier(name=name, kind=kind, trades=trades, rating=rating, approved_by=approved, status="approved",
                        project_types=["infra"] if "Roads" in trades else ["building"],
                        approval_date=date.today() - timedelta(days=200), approval_expiry=date.today() + timedelta(days=165)))


def seed_base(db: Session):
    seed_cost_codes(db)
    seed_admin(db)
    db.flush()
    seed_library(db)
    db.commit()
