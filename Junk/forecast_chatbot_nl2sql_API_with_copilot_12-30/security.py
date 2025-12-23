from typing import List
from db import _extract_table_names

# Role -> allowed tables policy (lower-case keys)
ROLE_TABLES = {
    "admin": ["meter_table", "customer_table", "revenue_data"],
    # planner MUST NOT access revenue_table / Revenue_data
    "planner": ["meter_table", "customer_table"]
}


def allowed_tables_for_role(role: str) -> List[str]:
    role = (role or "").lower()
    return ROLE_TABLES.get(role, [])


def extract_table_names(sql: str) -> List[str]:
    # wrapper to centralize extraction in case parsing logic changes
    return _extract_table_names(sql)
