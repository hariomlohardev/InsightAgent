# InsightAgent SDK

`pip install -e sdk` → `from insightagent import InsightAgent`

Works with `docker-compose up` (local, `CLOUD=false`) and cloud (`INSIGHTAGENT_URL`).

```python
from insightagent import InsightAgent
import pandas as pd

agent = InsightAgent(url="http://localhost:8000")  # or https://cloud.insightagent.com
df = pd.read_csv("sales.csv")
agent.upload(df, name="sales.csv")
print(agent.chat("top 5 products by sales"))
```

See `sdk/insightagent/__init__.py`.
