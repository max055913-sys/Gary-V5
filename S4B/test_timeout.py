import io
import json
import unittest
from unittest.mock import patch

from v5.gary_v5.module_rules import RULES
from v5.gary_v5.responses_stream import StreamCapture, StreamFailure
from v5.gary_v5.sol_web_profile import parameters, profile_version, transport_timeout, validate


class DeadlineTests(unittest.TestCase):
    def test_all_streaming_modules(self):
        for module in RULES:
            with self.subTest(module=module):
                body={'module':module,'question':'TEST délai','documentary_web_profile':profile_version(module)}
                request={**parameters(module),'input':json.dumps(body),'instructions':'TEST'}
                self.assertTrue(validate(request))
                self.assertEqual(transport_timeout(request),180)
                self.assertFalse(validate({**request,'timeout':180}))
                self.assertEqual(transport_timeout({**request,'timeout':180}),60)

    def test_luna_and_non_streaming(self):
        self.assertEqual(transport_timeout({'model':'gpt-6-luna'}),60)
        self.assertEqual(transport_timeout({'model':'gpt-6.1-sol','stream':False}),60)

    def test_deadline_without_wait(self):
        capture=StreamCapture('gpt-6.1-sol')
        events = (
            {"type": "response.created", "response": {"model": "gpt-6.1-sol", "status": "in_progress"}},
            {"type": "response.output_text.delta", "output_index": 0, "content_index": 0,
             "delta": "TEST début de réponse."},
        )
        capture.feed("".join(f"data: {json.dumps(event)}\n\n" for event in events).encode())
        with patch('v5.gary_v5.responses_stream.time.monotonic',return_value=180), self.assertRaises(StreamFailure):
            capture.consume(io.BytesIO(),deadline=180)
        self.assertFalse(capture.terminal)
        partial=capture.partial()
        self.assertEqual(partial['incomplete_details']['reason'],'stream_interrupted')
        self.assertIsNone(partial['usage'])


if __name__=='__main__':
    unittest.main()

