// Keep compatibility with Flutter versions before the Material UI package split.
// ignore: deprecated_member_use
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:homecue_mobile/main.dart';

void main() {
  testWidgets('Signed-out caregiver can open server settings', (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    await tester.pumpWidget(const HomeCueApp());
    await tester.pumpAndSettle();
    expect(find.text('Welcome home.'), findsOneWidget);
    await tester.tap(find.byTooltip('Server settings'));
    await tester.pumpAndSettle();
    expect(find.text('Server address'), findsOneWidget);
    expect(find.byType(AlertDialog), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
