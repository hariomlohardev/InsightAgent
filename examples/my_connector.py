"""Example connector — copy to your own package and register via entry_points."""
import pandas as pd
from app.plugins import BaseConnector, register_connector

@register_connector
class MyConnector(BaseConnector):
    kind = "my_db"
    display_name = "My Example DB"
    params_schema = [
        {"name":"host","label":"Host","type":"text","placeholder":"localhost"},
        {"name":"query","label":"SQL","type":"text","placeholder":"SELECT * FROM my_table LIMIT 100"},
    ]

    def fetch(self, params: dict, limit: int = 1000) -> pd.DataFrame:
        # In real connector, connect to DB/API here
        # For demo, return sample
        return pd.DataFrame({"id":[1,2,3],"value":[10,20,30]})

    def validate(self, params: dict) -> str | None:
        if not params.get("host"):
            return "host required"
        if not params.get("query"):
            return "query required"
        return None
