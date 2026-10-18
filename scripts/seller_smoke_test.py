"""Sotuvchi Desk amallarini HTTP orqali sinaydi. Ishga tushirish: bench start ishlab turganda
   cd ~/marketplace-bench && env/bin/python apps/marketplace/scripts/seller_smoke_test.py
"""
import json, sys
import requests

BASE = "http://127.0.0.1:8001"
results = []

def check(name, ok, info=""):
    results.append(ok)
    print(("✅" if ok else "❌"), name, ("— " + str(info)[:160]) if info else "")

def session(user):
    s = requests.Session()
    r = s.post(f"{BASE}/api/method/login", data={"usr": user, "pwd": "Test12345!"})
    assert r.ok, r.text
    return s

def call(s, method, **data):
    r = s.post(f"{BASE}/api/method/{method}", data={k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in data.items()})
    return r

def err(r):
    try:
        j = r.json()
        msgs = j.get("_server_messages")
        if msgs:
            return "; ".join(json.loads(m).get("message", "") for m in json.loads(msgs))
        return j.get("exc_type") or r.text[:150]
    except Exception:
        return r.text[:150]

s = session("nafis@test.uz")

# 1. Item formasini ochish (Desk new Item ochganda doctype meta yuklanadi)
r = call(s, "frappe.desk.form.load.getdoctype", doctype="Item")
check("Item formasini ochish (meta)", r.ok, "" if r.ok else err(r))

# 2. Link maydonlari uchun qidiruv (formada dropdownlar)
for dt in ["Item Group", "UOM", "Price List", "Warehouse", "Brand", "Item Attribute", "Shop"]:
    r = call(s, "frappe.desk.search.search_link", doctype=dt, txt="", page_length=5)
    vals = [x.get("value") for x in r.json().get("message", [])] if r.ok else None
    check(f"Link qidiruv: {dt}", r.ok, vals if r.ok else err(r))

# 3. Desk orqali Item saqlash (savedocs — formadagi Save tugmasi)
item = {"doctype": "Item", "item_code": "smoke-test", "item_name": "Zig'ir ko'ylak", "item_group": "Consumable",
        "stock_uom": "Nos", "is_stock_item": 1, "is_published": 0, "mxik_code": "06205200001000000",
        "shop": "nafis-tekstil", "__islocal": 1, "name": "new-item-1"}
# Bitta doimiy test tovar (saytda ko'rinmaydi): har ishga tushganda yangi tovar yaratilmaydi
existing = call(s, "frappe.client.get_value", doctype="Item", filters={"name": "nafis-tekstil-smoke-test"}, fieldname="name")
if existing.ok and existing.json().get("message"):
    name = "nafis-tekstil-smoke-test"
    r = call(s, "frappe.client.set_value", doctype="Item", name=name, fieldname="item_name", value="Smoke test")
    check("Item saqlash (mavjud test tovarni yangilash)", r.ok, name if r.ok else err(r))
else:
    r = call(s, "frappe.desk.form.save.savedocs", doc=item, action="Save")
    name = r.json()["docs"][0]["name"] if r.ok else None
    check("Item saqlash (Desk Save)", r.ok, name if r.ok else err(r))

# 4. Narx qo'shish
if name:
    r = call(s, "frappe.desk.form.save.savedocs", action="Save", doc={
        "doctype": "Item Price", "item_code": name, "price_list": "Standard Selling",
        "price_list_rate": 189000, "__islocal": 1, "name": "new-item-price-1"})
    if not r.ok and "Item Price appears multiple times" in err(r):
        check("Item Price (allaqachon bor)", True)
    else:
        shop = r.json()["docs"][0].get("shop") if r.ok else None
        check("Item Price saqlash", r.ok and shop == "nafis-tekstil", f"shop={shop}" if r.ok else err(r))

# 5. Ro'yxatlar
for dt in ["Item", "Item Price", "Sales Order", "Delivery Note", "Warehouse", "Shop", "Stock Reconciliation"]:
    r = call(s, "frappe.client.get_list", doctype=dt, fields=["name"], limit_page_length=50)
    check(f"Ro'yxat: {dt}", r.ok, [x["name"] for x in r.json()["message"]] if r.ok else err(r))

# 6. Qoldiq kiritish — o'z ombori
if name:
    sr = {"doctype": "Stock Reconciliation", "company": "Marketplace", "purpose": "Stock Reconciliation", "name": "new-stock-reconciliation-1",
          "__islocal": 1, "items": [{"doctype": "Stock Reconciliation Item", "item_code": name,
          "warehouse": "nafis-tekstil - M", "qty": __import__("time").time_ns() % 9000 + 10, "valuation_rate": 1, "__islocal": 1}]}
    r = call(s, "frappe.desk.form.save.savedocs", doc=sr, action="Submit")
    check("Qoldiq kiritish (o'z ombori, Submit)", r.ok, r.json()["docs"][0]["name"] if r.ok else err(r))

# 7. Qoldiq kiritish — BOSHQA do'kon ombori (taqiqlanishi kerak)
r = call(s, "frappe.desk.form.save.savedocs", action="Save", doc={
    "doctype": "Stock Reconciliation", "company": "Marketplace", "purpose": "Stock Reconciliation", "__islocal": 1, "name": "new-stock-reconciliation-2",
    "items": [{"doctype": "Stock Reconciliation Item", "item_code": "bunyod-mebel-futbolka-01",
               "warehouse": "bunyod-mebel - M", "qty": 999, "valuation_rate": 1, "__islocal": 1}]})
check("Boshqa do'kon omboriga qoldiq kiritish TAQIQLANGAN", not r.ok, err(r))

# 8. Boshqa do'kon tovarini o'zgartirish (taqiqlanishi kerak)
r = call(s, "frappe.client.set_value", doctype="Item", name="bunyod-mebel-futbolka-01", fieldname="item_name", value="hack")
check("Boshqa do'kon tovarini o'zgartirish TAQIQLANGAN", not r.ok, err(r))

# 9. Shop'ni o'zgartirish (sotuvchi faqat o'qiydi)
r = call(s, "frappe.client.set_value", doctype="Shop", name="nafis-tekstil", fieldname="enable_payme", value=0)
check("Shop sozlamasini sotuvchi o'zgartira olmaydi", not r.ok, err(r))

print(f"\n{sum(results)}/{len(results)} o'tdi")
