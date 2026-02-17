import app.routers.events as events
from app.routers.request_schemas import AddSymposiumRequest, TimeframeWindow

def test_add_symposium():
    payload = AddSymposiumRequest(
        rooms_available=5,
        symposium_name="Spring Symposium",
        timeframes=[
            TimeframeWindow(
                end_time="2026-04-20T12:00:00Z",
                start_time="2026-04-20T09:00:00Z",
            ),
            TimeframeWindow(
                end_time="2026-04-21T16:00:00Z",
                start_time="2026-04-21T13:00:00Z",
            )
        ]
    )
    events.add_symposium(payload)

def main():
    test_add_symposium()

if __name__ == "__main__":
    main()
