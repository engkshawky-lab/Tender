"""Generate sample owner files used by the tests and the demo data.
python samples/make_samples.py  →  samples/*.xlsx, samples/*.docx"""
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

HERE = Path(__file__).parent


def building_boq():
    wb = Workbook()
    ws = wb.active
    ws.title = "المقايسة"
    ws.sheet_view.rightToLeft = True
    ws.merge_cells("A1:F1")
    ws["A1"] = "مقايسة أعمال مبنى إداري - التجمع الخامس"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A2:F2")
    ws["A2"] = "المالك: شركة النخيل للتطوير العقاري"
    hdr = ["رقم البند", "بيان الأعمال", "الوحدة", "الكمية", "الفئة", "الإجمالي"]
    for c, h in enumerate(hdr, start=1):
        ws.cell(4, c, h).font = Font(bold=True)
    rows = [
        ("1", "أعمال الحفر والردم", None, None),
        ("1/1", "بالمتر المكعب حفر في أي نوع من التربة حتى المنسوب المطلوب مع نقل المخلفات خارج الموقع", "م3", 1800),
        ("1/2", "بالمتر المكعب ردم بالرمل النظيف على طبقات مع الدك والرش بالمياه", "م3", 900),
        ("2", "أعمال الخرسانات", None, None),
        ("2/1", "بالمتر المكعب توريد وصب خرسانة عادية للأساسات", "م3", 160),
        ("2/2", "بالمتر المكعب توريد وصب خرسانة مسلحة للقواعد والسملات بمحتوى أسمنت 350 كجم/م3", None, None),
        ("", "شاملة الشدات وحديد التسليح طبقا للرسومات والمواصفات", "م3", 420),
        ("2/3", "بالمتر المكعب خرسانة مسلحة للأعمدة والحوائط الخرسانية", "م3", 260),
        ("2/4", "بالمتر المكعب خرسانة مسلحة للأسقف والكمرات", "م3", 780),
        ("3", "أعمال المباني والتشطيبات", None, None),
        ("3/1", "بالمتر المربع مباني طوب أسمنتي مصمت سمك 25 سم", "م2", 3200),
        ("3/2", "بالمتر المربع بياض داخلي للحوائط والأسقف", "م2", 9800),
        ("3/3", "بالمتر المربع توريد وتركيب بورسلين أرضيات مستورد مقاس 60×60", "م2", 2400),
        ("3/4", "بالمتر المربع دهانات بلاستيك 3 أوجه", "م2", 9800),
        ("3/5", "بالمتر المربع أسقف معلقة جبسوم بورد", "م2", 1500),
        ("4", "الأعمال الكهروميكانيكية", None, None),
        ("4/1", "بالمتر الطولي توريد وتمديد مواسير تغذية PPR", "م.ط", 1600),
        ("4/2", "بالعدد توريد وتركيب وحدات تكييف سبليت 3 حصان", "عدد", 48),
        ("4/3", "بالمتر الطولي توريد وتمديد كابلات نحاس 4×16 مم2", "م.ط", 2200),
        ("4/4", "بالعدد توريد وتركيب لوحات توزيع فرعية", "عدد", 14),
        ("4/5", "بالعدد تركيب فقط كشافات إنارة (توريد المالك)", "عدد", 620),
        ("5", "الفرش", None, None),
        ("5/1", "بالعدد توريد وتركيب مكاتب عمل بالكراسي", "عدد", 120),
        ("5/2", "مبلغ احتياطي لأعمال اللاندسكيب (مبلغ مقطوع)", "مقطوعية", 1),
    ]
    r = 5
    for ref, desc, unit, qty in rows:
        ws.cell(r, 1, ref)
        ws.cell(r, 2, desc).alignment = Alignment(wrap_text=True)
        if unit:
            ws.cell(r, 3, unit)
            ws.cell(r, 4, qty)
            ws.cell(r, 6, f"=D{r}*E{r}")
        else:
            if ref:
                ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6) if not ref.count("/") else None
                ws.cell(r, 2).font = Font(bold=True) if not ref.count("/") else Font()
        r += 1
    ws.cell(r, 2, "الإجمالي")
    ws.cell(r, 6, f"=SUM(F5:F{r-1})")
    ws.column_dimensions["B"].width = 70
    wb.save(HERE / "owner_boq_building_ar.xlsx")


def infra_boq():
    wb = Workbook()
    for title, rows in {
        "Bill 1 - Roads": [
            ("A", "ROAD WORKS", None, None),
            ("A.1", "Excavation in all types of soil for road formation", "m3", 12000),
            ("A.2", "Supply and lay aggregate sub-base course 25 cm compacted", "m3", 6500),
            ("A.3", "Prime coat MC-70", "m2", 26000),
            ("A.4", "Asphalt binder course 6 cm", "m2", 26000),
            ("A.5", "Asphalt wearing course 5 cm", "m2", 26000),
            ("A.6", "Precast concrete curbs 15x30", "m", 5200),
        ],
        "Bill 2 - Networks": [
            ("B", "WATER & SEWER NETWORKS", None, None),
            ("B.1", "Supply and install HDPE water pipes PE100 PN10 dia 200 mm", "m", 3400),
            ("B.2", "Supply and install gate valves dia 200 mm complete with chamber", "no", 24),
            ("B.3", "Supply and install uPVC sewer pipes dia 315 mm", "m", 2900),
            ("B.4", "Construct precast manholes depth up to 3 m", "no", 58),
            ("C", "ELECTRICAL & MECHANICAL", None, None),
            ("C.1", "Supply and install street lighting poles 10 m with LED luminaire", "no", 140),
            ("C.2", "Supply and lay LV cable 4x35 mm2 XLPE", "m", 6200),
            ("C.3", "Supply and install submersible sewage pumps 30 l/s (lifting station)", "no", 2),
            ("C.4", "Provisional sum for utility authority connections", "ls", 1),
        ],
    }.items():
        ws = wb.create_sheet(title)
        ws["A1"] = "BILL OF QUANTITIES — 6th District Infrastructure"
        ws.merge_cells("A1:F1")
        for c, h in enumerate(["Item", "Description", "Unit", "Qty", "Rate", "Amount"], start=1):
            ws.cell(3, c, h).font = Font(bold=True)
        r = 4
        for ref, desc, unit, qty in rows:
            ws.cell(r, 1, ref)
            ws.cell(r, 2, desc)
            if unit:
                ws.cell(r, 3, unit)
                ws.cell(r, 4, qty)
                ws.cell(r, 6, f"=D{r}*E{r}")
            r += 1
        ws.cell(r, 2, "Total carried to summary")
    wb.remove(wb["Sheet"])
    wb.save(HERE / "owner_boq_infra_en.xlsx")


def conditions_doc():
    d = Document()
    d.add_heading("الشروط الخاصة للمناقصة - مبنى إداري التجمع الخامس", 1)
    for p in [
        "المالك: شركة النخيل للتطوير العقاري. الاستشاري: المكتب الهندسي المتحد.",
        "آخر موعد لتقديم العطاءات هو 2026-12-10، وآخر موعد لتلقي الاستفسارات 2026-11-25، وزيارة الموقع يوم 2026-11-18.",
        "مدة التنفيذ 14 شهرا من تاريخ استلام الموقع.",
        "غرامة التأخير 1% من قيمة العقد عن كل أسبوع تأخير بحد أقصى 10% من قيمة العقد.",
        "يصرف للمقاول دفعة مقدمة بنسبة 10% مقابل خطاب ضمان بنفس القيمة، تستقطع من المستخلصات بنفس النسبة.",
        "يستقطع نسبة 5% من كل مستخلص كتأمين أعمال (Retention) ترد بعد الاستلام النهائي.",
        "تصرف المستخلصات خلال 45 يوما من تاريخ تقديمها للاستشاري.",
        "التأمين الابتدائي 2% من قيمة العطاء، والتأمين النهائي 5% من قيمة العقد.",
        "يلتزم المقاول بعمل وثيقة تأمين شامل على الأعمال (CAR) طوال مدة التنفيذ.",
        "الأسعار ثابتة ولا يجوز المطالبة بأي فروق أسعار طوال مدة التنفيذ.",
        "العملة: الجنيه المصري. مدة صلاحية العرض 90 يوما من تاريخ فتح المظاريف.",
        "قائمة الموردين المعتمدين للتكييف: Carrier, LG, Daikin. البورسلين: كليوباترا أو مستورد إسباني معتمد.",
        "مدة الضمان والصيانة سنة من تاريخ الاستلام الابتدائي.",
        "ملاحظة: الرسومات توضح سمك البلاطات 20 سم بينما المواصفات تنص على 18 سم.",
    ]:
        d.add_paragraph(p)
    d.save(HERE / "particular_conditions_ar.docx")


def priced_old_boq():
    """An old priced BOQ (as submitted in a past tender) — imported as a price reference."""
    from openpyxl import load_workbook
    building_boq()
    wb = load_workbook(HERE / "owner_boq_building_ar.xlsx")
    ws = wb.active
    rates = {"1/1": 95, "1/2": 310, "2/1": 3300, "2/3": 8900, "2/4": 9400, "3/1": 520, "3/2": 160, "3/3": 1480,
             "3/4": 125, "3/5": 610, "4/1": 260, "4/2": 61000, "4/3": 640, "4/4": 22500, "4/5": 190, "5/1": 11800, "5/2": 600000}
    for r in range(5, ws.max_row + 1):
        ref = ws.cell(r, 1).value
        if ref in rates:
            ws.cell(r, 5).value = rates[ref]
        if ref == "" or ref is None:
            if ws.cell(r, 3).value:  # continuation row of item 2/2
                ws.cell(r, 5).value = 8600
    wb.save(HERE / "priced_boq_2024_reference.xlsx")


def price_list():
    wb = Workbook()
    ws = wb.active
    ws.title = "قائمة أسعار"
    ws.append(["الكود", "الصنف", "الوحدة", "السعر", "العملة", "النوع", "تاريخ السعر", "المورد"])
    for row in [("M-CON-350", "خرسانة جاهزة 350 كجم/م3", "m3", 3350, "EGP", "خامات", "2026-10-25", "الشركة المصرية للخرسانة"),
                ("M-STL", "حديد تسليح", "ton", 40500, "EGP", "خامات", "2026-10-28", "حديد المصريين"),
                ("M-CAB-416", "كابل نحاس 4×16 مم2", "m", 310, "EGP", "خامات", "2026-10-20", "كابلات السويدي"),
                ("L-ELEC", "فني كهرباء + مساعد (يومية)", "day", 1300, "EGP", "عمالة", "2026-10-01", ""),
                ("E-CRANE", "ونش 25 طن (يوم)", "day", 9000, "EGP", "معدات", "2026-09-15", "")]:
        ws.append(list(row))
    wb.save(HERE / "reference_price_list.xlsx")


if __name__ == "__main__":
    building_boq()
    priced_old_boq()
    price_list()
    infra_boq()
    conditions_doc()
    print("samples written to", HERE)
