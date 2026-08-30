import 'dart:async';
import 'dart:convert';
import 'dart:io';

class BackendSocketMessage {
  const BackendSocketMessage({this.payload, this.text});

  final Map<String, dynamic>? payload;
  final String? text;
}

class ServerActivitySocketService {
  WebSocket? _socket;
  StreamSubscription<dynamic>? _subscription;
  final _controller = StreamController<BackendSocketMessage>.broadcast();

  Stream<BackendSocketMessage> get messages => _controller.stream;

  Future<void> connect(String url) async {
    await disconnect();

    final socket = await WebSocket.connect(url);
    _socket = socket;
    _subscription = socket.listen(
      _handleMessage,
      onDone: () => _controller.add(const BackendSocketMessage(text: 'closed')),
      onError: (Object error) => _controller.add(
        BackendSocketMessage(text: 'Socket error: $error'),
      ),
      cancelOnError: false,
    );
  }

  Future<void> disconnect() async {
    await _subscription?.cancel();
    _subscription = null;
    await _socket?.close();
    _socket = null;
  }

  Future<void> dispose() async {
    await disconnect();
    await _controller.close();
  }

  void _handleMessage(dynamic message) {
    final text = message.toString();
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map<String, dynamic>) {
        _controller.add(BackendSocketMessage(payload: decoded));
        return;
      }
    } on FormatException {
      // Plain text backend messages are still useful status updates.
    }

    _controller.add(BackendSocketMessage(text: text));
  }
}
