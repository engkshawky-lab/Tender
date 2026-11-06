"""Company defaults (spec rule 9: ratios & criteria live in Settings, editable from the UI — not hard-coded logic).
Values below are only starting points; tax rates in particular must be confirmed against the law in force."""

PROJECT_TYPES = {
    "building": {"ar": "متكامل (حفر وخرسانات + تشطيبات + MEP + فرش)", "en": "Integrated (Civil/Structure + Finishes + MEP + FF&E)"},
    "infra": {"ar": "بنية تحتية (ميكانيكا + كهرباء + شبكات + طرق)", "en": "Infrastructure (Mech + Elec + Networks + Roads)"},
}

SCOPES = {
    "supply": {"ar": "توريد", "en": "Supply"},
    "apply": {"ar": "تركيب / تنفيذ", "en": "Apply"},
    "supply_apply": {"ar": "توريد وتركيب", "en": "Supply + Apply"},
}

DEFAULT_SETTINGS = {
    "company": {"name": "", "base_currency": "EGP"},
    "fx_rates": {"USD": 48.5, "EUR": 52.5, "as_of": "set-me"},
    "taxes": [
        {"name": "VAT / ضريبة القيمة المضافة", "rate_pct": 14, "mode": "on_top"},
        {"name": "Stamp & other duties / دمغات ورسوم", "rate_pct": 0, "mode": "in_price"},
    ],
    "pricing_defaults": {
        "markup_pct": 10, "ho_overhead_pct": 5, "general_contingency_pct": 2,
        "material_escalation_pct": 0, "fx_buffer_pct": 0,
        "performance_bond_pct": 5, "advance_guarantee_pct": 10, "bond_commission_pa_pct": 2,
        "insurance_pct": 0.3, "maintenance_months": 12, "bid_validity_days": 90,
        "advance_payment_pct": 10, "retention_pct": 5, "payment_delay_months": 2,
        "finance_rate_pa_pct": 25, "include_finance": True, "rate_decimals": 2,
    },
    "price_age_days": 90,          # older prices are flagged (spec rule 4)
    "outlier_pct": 35,             # deviation from historical rates that triggers a flag
    "gonogo": {
        "threshold_pct": 60,
        "criteria": [
            {"key": "experience", "ar": "خبرتنا في نوع المشروع", "en": "Experience in project type", "weight": 20},
            {"key": "capacity", "ar": "الحجم مقابل طاقة الشركة الحالية", "en": "Size vs current capacity", "weight": 20},
            {"key": "owner_payment", "ar": "التزام المالك بالصرف", "en": "Owner payment record", "weight": 20},
            {"key": "competition", "ar": "المنافسة", "en": "Competition", "weight": 15},
            {"key": "risk", "ar": "المخاطر", "en": "Risk level", "weight": 15},
            {"key": "time", "ar": "الوقت المتاح للتسعير", "en": "Time available to price", "weight": 10},
        ],
    },
    # technical vs financial evaluation of supplier / subcontractor quotations
    "quote_evaluation": {
        "technical_weight": 40, "financial_weight": 60, "technical_pass_pct": 60,
        "criteria": [
            {"key": "spec_compliance", "ar": "مطابقة المواصفات والكراسة", "en": "Compliance with specs", "weight": 30},
            {"key": "approved_brand", "ar": "ماركة / مورد معتمد لدى المالك", "en": "Approved brand / vendor", "weight": 15},
            {"key": "experience", "ar": "الخبرة وسابقة الأعمال", "en": "Experience & references", "weight": 15},
            {"key": "lead_time", "ar": "مدة التوريد والتنفيذ", "en": "Lead time / programme", "weight": 15},
            {"key": "payment_terms", "ar": "شروط الدفع", "en": "Payment terms", "weight": 10},
            {"key": "scope_completeness", "ar": "اكتمال النطاق وقلة الاستثناءات", "en": "Scope completeness / exclusions", "weight": 10},
            {"key": "warranty", "ar": "الضمان وخدمة ما بعد البيع", "en": "Warranty & after-sales", "weight": 5},
        ],
    },
    # construction cost index by month (e.g. CAPMAS building-materials bulletin) — normalises old reference prices
    "cost_indices": {"source": "", "values": {}},
    # reusable clarifications / exclusions for the financial offer letter
    "clarifications_library": [
        {"ar": "الأسعار لا تشمل أي أعمال غير واردة صراحة بالمقايسة.", "en": "Prices exclude any work not expressly listed in the BOQ."},
        {"ar": "الأسعار مبنية على الكميات الواردة بالمقايسة وتخضع للقياس الفعلي.", "en": "Prices are based on BOQ quantities and subject to re-measurement."},
        {"ar": "توفير المياه والكهرباء اللازمة للتنفيذ على نفقة المالك.", "en": "Water and power for construction to be provided by the owner."},
        {"ar": "الأسعار مبنية على سعر صرف الدولار الوارد بالعرض، وأي تغير يزيد عن 5% يُعاد التسعير على أساسه للبنود المستوردة.", "en": "Prices are based on the stated USD rate; changes above 5 % re-price imported items."},
        {"ar": "التصاريح والرسوم الحكومية على نفقة المالك ما لم يُذكر خلاف ذلك.", "en": "Permits and authority fees by the owner unless stated otherwise."},
        {"ar": "مدة التوريد للبنود المستوردة تبدأ من تاريخ اعتماد العينات وصرف الدفعة المقدمة.", "en": "Lead times for imported items start from sample approval and advance payment."},
    ],
    "waste_defaults": {"concrete": 2.5, "rebar": 5, "blocks": 5, "tiles": 7, "paint": 5, "pipes": 3, "cables": 3, "asphalt": 3},
    "site_visit_templates": {
        "building": [
            {"key": "soil", "ar": "التربة ومنسوب المياه الجوفية", "en": "Soil & ground water"},
            {"key": "access", "ar": "المداخل وطرق الوصول", "en": "Access roads & gates"},
            {"key": "storage", "ar": "أماكن التشوين والتنزيل", "en": "Storage & unloading areas"},
            {"key": "utilities", "ar": "المرافق (مياه / كهرباء) للموقع", "en": "Site utilities (water / power)"},
            {"key": "neighbours", "ar": "الجوار والمباني الملاصقة", "en": "Neighbours & adjacent buildings"},
            {"key": "sources", "ar": "المسافة من مصادر الخامات", "en": "Distance to material sources"},
            {"key": "owner_rules", "ar": "اشتراطات المالك ومواعيد العمل المسموحة", "en": "Owner rules & permitted working hours"},
            {"key": "existing_mep", "ar": "حالة الأعمال الكهروميكانيكية القائمة", "en": "Existing MEP condition"},
        ],
        "infra": [
            {"key": "route", "ar": "مسار الأعمال والعوائق", "en": "Route & obstructions"},
            {"key": "existing_utilities", "ar": "المرافق القائمة (كابلات / مواسير)", "en": "Existing utilities (cables / pipes)"},
            {"key": "traffic", "ar": "تحويلات المرور", "en": "Traffic diversions"},
            {"key": "groundwater", "ar": "المياه الجوفية ونزح المياه", "en": "Groundwater & dewatering"},
            {"key": "soil", "ar": "نوع التربة وصلاحية الردم", "en": "Soil type & backfill suitability"},
            {"key": "permits", "ar": "التصاريح والجهات المختصة", "en": "Permits & authorities"},
            {"key": "storage", "ar": "أماكن التشوين والمعسكر", "en": "Storage yard & camp"},
            {"key": "sources", "ar": "المسافة من مصادر الخامات والمحاجر", "en": "Distance to quarries / sources"},
        ],
    },
    "indirect_templates": {
        "building": [
            {"key": "pm", "category": "site_staff", "ar": "مدير مشروع", "en": "Project manager", "kind": "time", "monthly_cost": 60000, "quantity": 1},
            {"key": "site_eng", "category": "site_staff", "ar": "مهندس موقع", "en": "Site engineer", "kind": "time", "monthly_cost": 25000, "quantity": 2},
            {"key": "mep_eng", "category": "site_staff", "ar": "مهندس كهروميكانيكا", "en": "MEP engineer", "kind": "time", "monthly_cost": 25000, "quantity": 1},
            {"key": "qs", "category": "site_staff", "ar": "مهندس حصر / مكتب فني", "en": "QS / technical office", "kind": "time", "monthly_cost": 22000, "quantity": 1},
            {"key": "hse", "category": "site_staff", "ar": "مسؤول سلامة", "en": "HSE officer", "kind": "time", "monthly_cost": 15000, "quantity": 1},
            {"key": "security", "category": "services", "ar": "حراسة", "en": "Security", "kind": "time", "monthly_cost": 12000, "quantity": 1},
            {"key": "cars", "category": "transport", "ar": "سيارات", "en": "Vehicles", "kind": "time", "monthly_cost": 18000, "quantity": 1},
            {"key": "utilities", "category": "services", "ar": "مياه وكهرباء الموقع", "en": "Site water & power", "kind": "time", "monthly_cost": 8000, "quantity": 1},
            {"key": "mobilization", "category": "setup", "ar": "التجهيز والفك", "en": "Mobilization & demobilization", "kind": "fixed", "amount": 150000},
            {"key": "offices", "category": "setup", "ar": "مكاتب مؤقتة", "en": "Temporary offices", "kind": "fixed", "amount": 120000},
            {"key": "tests", "category": "tests", "ar": "الاختبارات", "en": "Testing", "kind": "fixed", "amount": 50000},
        ],
        "infra": [
            {"key": "pm", "category": "site_staff", "ar": "مدير مشروع", "en": "Project manager", "kind": "time", "monthly_cost": 60000, "quantity": 1},
            {"key": "site_eng", "category": "site_staff", "ar": "مهندس موقع", "en": "Site engineer", "kind": "time", "monthly_cost": 25000, "quantity": 3},
            {"key": "surveyor", "category": "site_staff", "ar": "مساح", "en": "Surveyor", "kind": "time", "monthly_cost": 15000, "quantity": 2},
            {"key": "hse", "category": "site_staff", "ar": "مسؤول سلامة", "en": "HSE officer", "kind": "time", "monthly_cost": 15000, "quantity": 1},
            {"key": "traffic", "category": "services", "ar": "تحويلات مرورية ولافتات", "en": "Traffic management", "kind": "time", "monthly_cost": 20000, "quantity": 1},
            {"key": "cars", "category": "transport", "ar": "سيارات", "en": "Vehicles", "kind": "time", "monthly_cost": 18000, "quantity": 2},
            {"key": "camp", "category": "setup", "ar": "معسكر وتشوين", "en": "Camp & yard", "kind": "fixed", "amount": 250000},
            {"key": "mobilization", "category": "setup", "ar": "التجهيز والفك", "en": "Mobilization & demobilization", "kind": "fixed", "amount": 200000},
            {"key": "permits", "category": "fees", "ar": "تصاريح ورسوم", "en": "Permits & fees", "kind": "fixed", "amount": 100000},
            {"key": "tests", "category": "tests", "ar": "الاختبارات والمعامل", "en": "Testing & labs", "kind": "fixed", "amount": 80000},
        ],
    },
    "submission_checklist": [
        {"ar": "خطاب العطاء موقع ومختوم", "en": "Signed & stamped form of tender"},
        {"ar": "خطاب الضمان الابتدائي", "en": "Bid bond"},
        {"ar": "المقايسة المسعرة بنموذج المالك (موقعة على كل صفحة)", "en": "Priced BOQ in owner format (initialled)"},
        {"ar": "العرض الفني", "en": "Technical proposal"},
        {"ar": "السجل التجاري والبطاقة الضريبية", "en": "Commercial register & tax card"},
        {"ar": "شهادة التصنيف", "en": "Classification certificate"},
        {"ar": "الملاحق موقعة", "en": "Signed addenda"},
        {"ar": "المظاريف (فني / مالي) والنسخ المطلوبة", "en": "Envelopes (technical / financial) & copies"},
    ],
}

DOC_TYPES = ["invitation", "drawings", "specs", "boq", "general_conditions", "particular_conditions",
             "addendum", "quotation", "site_photo", "submission", "other"]

# Cost-code tree: division (L1) → work type (L2) → standard item (L3).  Keywords drive offline auto-coding.
COST_CODES = [
    # ---- building / integrated
    ("B01", "أعمال عامة وتمهيدية", "General & preliminaries", "building", []),
    ("B02", "أعمال الحفر والردم", "Earthworks", "building", [
        ("B02.01", "حفر", "Excavation", "m3", "حفر excavation حفريات"),
        ("B02.02", "ردم وإحلال", "Backfill & replacement", "m3", "ردم احلال إحلال backfill dakk دك"),
        ("B02.03", "نزح مياه", "Dewatering", "ls", "نزح dewatering"),
    ]),
    ("B03", "الخرسانات", "Concrete", "building", [
        ("B03.01", "خرسانة عادية", "Plain concrete", "m3", "خرسانة عادية plain concrete blinding"),
        ("B03.02", "خرسانة مسلحة أساسات", "RC foundations", "m3", "مسلحة قواعد اساسات أساسات لبشة footing raft foundation"),
        ("B03.03", "خرسانة مسلحة أعمدة وحوائط", "RC columns & walls", "m3", "مسلحة اعمدة أعمدة حوائط columns walls"),
        ("B03.04", "خرسانة مسلحة أسقف وكمرات", "RC slabs & beams", "m3", "مسلحة اسقف أسقف بلاطات كمرات slab beams"),
        ("B03.05", "حديد تسليح", "Reinforcement steel", "ton", "حديد تسليح rebar reinforcement"),
    ]),
    ("B04", "المباني", "Masonry", "building", [
        ("B04.01", "مباني طوب", "Block / brick walls", "m2", "مباني طوب بلوك block brick wall"),
    ]),
    ("B05", "العزل", "Insulation & waterproofing", "building", [
        ("B05.01", "عزل رطوبة ومائي", "Waterproofing", "m2", "عزل رطوبة مائي بيتومين waterproofing membrane"),
        ("B05.02", "عزل حراري", "Thermal insulation", "m2", "عزل حراري thermal foam"),
    ]),
    ("B06", "التشطيبات", "Finishes", "building", [
        ("B06.01", "بياض ومحارة", "Plastering", "m2", "بياض محارة لياسة plaster"),
        ("B06.02", "أرضيات وتكسيات", "Flooring & cladding", "m2", "سيراميك بورسلين رخام جرانيت ارضيات أرضيات تكسيات ceramic porcelain marble granite tiles flooring"),
        ("B06.03", "دهانات", "Painting", "m2", "دهان دهانات بلاستيك paint painting emulsion"),
        ("B06.04", "أسقف معلقة وجبس", "Ceilings & gypsum board", "m2", "جبس جبسوم بورد اسقف معلقة gypsum ceiling"),
        ("B06.05", "أبواب وشبابيك", "Doors & windows", "no", "باب ابواب أبواب شباك شبابيك الوميتال door window aluminium"),
    ]),
    ("B07", "أعمال الصحي", "Plumbing", "building", [
        ("B07.01", "مواسير تغذية وصرف", "Supply & drainage pipes", "m", "مواسير صرف تغذية بي بي ار pvc ppr pipes drainage"),
        ("B07.02", "أجهزة صحية", "Sanitary fixtures", "no", "اطقم أطقم حمام خلاط حوض مرحاض sanitary wc basin mixer"),
    ]),
    ("B08", "مكافحة الحريق", "Fire fighting", "building", [
        ("B08.01", "شبكة رشاشات وحريق", "Sprinkler & FF network", "m", "حريق رشاشات sprinkler fire hose"),
    ]),
    ("B09", "التكييف والتهوية", "HVAC", "building", [
        ("B09.01", "وحدات تكييف", "AC units", "no", "تكييف وحدات سبليت تشيلر split chiller ac fcu vrf"),
        ("B09.02", "مجاري هواء", "Ductwork", "m2", "مجاري هواء دكت duct"),
    ]),
    ("B10", "الكهرباء", "Electrical", "building", [
        ("B10.01", "كابلات وأسلاك", "Cables & wires", "m", "كابل كابلات اسلاك أسلاك cable wire"),
        ("B10.02", "لوحات توزيع", "Distribution boards", "no", "لوحة لوحات توزيع db panel board"),
        ("B10.03", "إنارة ومخارج", "Lighting & outlets", "no", "كشاف كشافات انارة إنارة بريزة مفتاح luminaire lighting socket"),
    ]),
    ("B11", "التيار الخفيف", "Low current", "building", [
        ("B11.01", "شبكات بيانات وكاميرات", "Data, CCTV & fire alarm", "no", "شبكة بيانات كاميرات انذار إنذار data cctv fire alarm"),
    ]),
    ("B12", "الفرش والأثاث", "Furniture (FF&E)", "building", [
        ("B12.01", "أثاث مكتبي وموديولات", "Loose & fixed furniture", "no", "اثاث أثاث مكاتب كراسي دواليب مطبخ furniture desk chair wardrobe kitchen"),
    ]),
    # ---- infrastructure
    ("I01", "أعمال عامة وتمهيدية - بنية تحتية", "Infra general", "infra", []),
    ("I02", "الطرق", "Roads", "infra", [
        ("I02.01", "حفر وتسوية طرق", "Road earthworks", "m3", "حفر تسوية قطع ردم طرق earthwork cut fill grading"),
        ("I02.02", "طبقات أساس ومساعد", "Sub-base & base", "m3", "اساس مساعد أساس سن كسر sub-base base course aggregate"),
        ("I02.03", "رصف أسفلتي", "Asphalt", "m2", "اسفلت أسفلت رابطة سطحية تشريب asphalt binder wearing prime tack"),
        ("I02.04", "بردورات وأرصفة", "Curbs & sidewalks", "m", "بردورة بردورات رصيف انترلوك curb kerb sidewalk interlock"),
    ]),
    ("I03", "شبكات المياه", "Water networks", "infra", [
        ("I03.01", "مواسير مياه", "Water pipes", "m", "مياه مواسير hdpe upvc ductile ماسورة water pipe"),
        ("I03.02", "محابس وقطع", "Valves & fittings", "no", "محبس محابس valve fittings حنفية حريق hydrant"),
    ]),
    ("I04", "شبكات الصرف", "Sewer & drainage", "infra", [
        ("I04.01", "مواسير صرف", "Sewer pipes", "m", "صرف صحي مواسير gRP grp upvc sewer"),
        ("I04.02", "غرف تفتيش", "Manholes", "no", "غرفة غرف تفتيش manhole"),
        ("I04.03", "صرف أمطار", "Storm drainage", "m", "امطار أمطار storm gully"),
    ]),
    ("I05", "الكهرباء - بنية تحتية", "Infra electrical", "infra", [
        ("I05.01", "كابلات جهد متوسط ومنخفض", "MV / LV cables", "m", "كابل جهد متوسط منخفض mv lv cable"),
        ("I05.02", "محطات وأكشاك", "Substations & kiosks", "no", "محول محولات كشك محطة transformer substation kiosk rmu"),
        ("I05.03", "إنارة الشوارع", "Street lighting", "no", "اعمدة أعمدة انارة إنارة شوارع street lighting pole"),
    ]),
    ("I06", "الميكانيكا", "Mechanical", "infra", [
        ("I06.01", "طلمبات ومحطات رفع", "Pumps & lifting stations", "no", "طلمبة طلمبات محطة رفع pump lifting station"),
    ]),
    ("I07", "شبكات الاتصالات", "Telecom networks", "infra", [
        ("I07.01", "مواسير وكابلات اتصالات", "Telecom ducts & cables", "m", "اتصالات فايبر fiber telecom duct"),
    ]),
]
