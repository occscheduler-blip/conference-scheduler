from app.routers import schemas
import pandas as pd

df = pd.DataFrame(
    [
        {
            "id": 1234,
            "name": "test",
            "departments": [],
        }
    ]
)

test = schemas.Symposium.model_validate(df.iloc[0].to_dict())
print(test)
