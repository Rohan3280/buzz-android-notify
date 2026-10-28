import 'package:aebuzz/relay.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses a desktop pairing code', () {
    final code = PairingCode.tryParse('{"v":1,"server":"https://abc.trycloudflare.com/","pair":"p1","token":"t"}');
    expect(code, isNotNull);
    expect(code!.server, 'https://abc.trycloudflare.com');
    expect(code.pairId, 'p1');
    expect(code.token, 't');
  });

  test('reads Firebase options from the code', () {
    final code = PairingCode.tryParse(
      '{"v":1,"server":"https://x.test","pair":"p","token":"t",'
      '"fb":{"api_key":"k","app_id":"a","project_id":"proj","sender_id":"1"}}',
    );
    expect(code!.firebase, {'api_key': 'k', 'app_id': 'a', 'project_id': 'proj', 'sender_id': '1'});
  });

  test('ignores incomplete Firebase options', () {
    final code = PairingCode.tryParse('{"v":1,"server":"s","pair":"p","token":"t","fb":{"api_key":"k"}}');
    expect(code!.firebase, isNull);
  });

  test('rejects unrelated QR codes', () {
    expect(PairingCode.tryParse('https://example.com'), isNull);
    expect(PairingCode.tryParse('{"v":2,"server":"x","pair":"p","token":"t"}'), isNull);
    expect(PairingCode.tryParse(null), isNull);
  });
}
