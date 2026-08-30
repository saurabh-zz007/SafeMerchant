# SafeMerchant Frontend

Flutter desktop client for the SafeMerchant backend websocket stream.

## Run

Make sure the backend is running on port `8000`, then run:

```powershell
flutter create . --platforms=windows
flutter pub get
flutter run -d windows
```

To point at another backend:

```powershell
flutter run -d windows --dart-define=WS_BASE_URL=ws://localhost:8000
```

The app connects to:

```text
ws://localhost:8000/ws/disputes/{dispute_id}
```

After connecting, it sends the JSON webhook shown in the editor and displays each streamed node update from the backend.
