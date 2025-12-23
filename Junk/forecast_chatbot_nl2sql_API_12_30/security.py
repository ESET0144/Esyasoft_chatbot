def allowed_tables_for_role(role: str):
    if role == "admin":
        return ["meter_table", "customer_table", "Revenue_data"]
    return ["meter_table"]
