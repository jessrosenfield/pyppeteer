#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import unittest

from syncer import sync

from base import BaseTestCase


class TestNetworkEvent(BaseTestCase):
    @sync
    async def test_request(self):
        requests = []
        self.page.on('request', lambda req: requests.append(req))
        await self.page.goto(self.url + 'empty')
        self.assertEqual(len(requests), 1)
        req = requests[0]
        self.assertEqual(req.url, self.url + 'empty')
        self.assertEqual(req.resourceType, 'document')
        self.assertEqual(req.method, 'GET')
        self.assertTrue(req.response)
        self.assertEqual(req.frame, self.page.mainFrame)
        self.assertEqual(req.frame.url, self.url + 'empty')

    @sync
    async def test_request_post(self):
        from tornado.web import RequestHandler

        class PostHandler(RequestHandler):
            def post(self):
                self.write('')

        self.app.add_handlers('localhost', [('/post', PostHandler)])
        requests = []
        self.page.on('request', lambda req: requests.append(req))
        await self.page.evaluate('fetch("./post", {method: "POST", body: JSON.stringify({foo: "bar"})})')  # noqa: E501
        self.assertEqual(len(requests), 1)
        req = requests[0]
        self.assertTrue(req)
        self.assertEqual(req.postData, '{"foo":"bar"}')

    @sync
    async def test_reponse(self):
        responses = []
        self.page.on('response', lambda res: responses.append(res))
        await self.page.goto(self.url + 'static/simple.json')
        self.assertEqual(len(responses), 1)
        res = responses[0]
        self.assertTrue(res)
        self.assertEqual(await res.text(), '{"foo": "bar"}\n')
        self.assertEqual(await res.json(), {'foo': 'bar'})

    @unittest.skip('This test hangs')
    @sync
    async def test_not_report_body_unless_finished(self):
        await self.page.goto(self.url + 'empty')
        serverResponses = []

        from tornado.web import RequestHandler

        class GetHandler(RequestHandler):
            def get(self):
                serverResponses.append(self)
                self.write('hello ')

        self.app.add_handlers('localhost', [('/get', GetHandler)])
        pageResponse = asyncio.get_event_loop().create_future()
        finishedRequests = []
        self.page.on('response', lambda res: pageResponse.set_result(res))
        self.page.on('requestfinished', lambda: finishedRequests.append(True))

        asyncio.ensure_future(
            self.page.evaluate('fetch("./get", {method: "GET"})'))
        response = await pageResponse
        self.assertTrue(serverResponses)
        self.assertTrue(response)
        self.assertIn(response.status, [200, 304])
        self.assertFalse(finishedRequests)

        responseText = response.text()
        serverResponses[0].write('wor')
        serverResponses[0].finish('ld!')
        self.assertEqual(await responseText, 'hello world!')

    @sync
    async def test_request_failed(self):
        await self.page.setRequestInterception(True)

        async def interception(req):
            if req.url.endswith('css'):
                await req.abort()
            else:
                await req.continue_()

        self.page.on(
            'request', lambda req: asyncio.ensure_future(interception(req)))

        failedRequests = []
        self.page.on('requestfailed', lambda req: failedRequests.append(req))
        await self.page.goto(self.url + 'static/one-style.html')
        self.assertEqual(len(failedRequests), 1)
        self.assertIn('one-style.css', failedRequests[0].url)
        self.assertIsNone(failedRequests[0].response)
        self.assertEqual(failedRequests[0].resourceType, 'stylesheet')
        self.assertEqual(
            failedRequests[0].failure()['errorText'], 'net::ERR_FAILED')
        self.assertTrue(failedRequests[0].frame)

    @sync
    async def test_request_finished(self):
        requests = []
        self.page.on('requestfinished', lambda req: requests.append(req))
        await self.page.goto(self.url + 'empty')

        self.assertEqual(len(requests), 1)
        req = requests[0]
        self.assertEqual(req.url, self.url + 'empty')
        self.assertTrue(req.response)
        self.assertEqual(req.frame, self.page.mainFrame)
        self.assertEqual(req.frame.url, self.url + 'empty')

    @sync
    async def test_events_order(self):
        events = []
        self.page.on('request', lambda req: events.append('request'))
        self.page.on('response', lambda res: events.append('response'))
        self.page.on(
            'requestfinished', lambda req: events.append('requestfinished'))
        await self.page.goto(self.url + 'empty')
        self.assertEqual(events, ['request', 'response', 'requestfinished'])

    @sync
    async def test_redirects(self):
        events = []
        self.page.on('request', lambda req: events.append(
            '{} {}'.format(req.method, req.url)))
        self.page.on('response', lambda res: events.append(
            '{} {}'.format(res.status, res.url)))
        self.page.on('requestfinished', lambda req: events.append(
            'DONE {}'.format(req.url)))
        self.page.on('requestfailed', lambda req: events.append(
            'FAIL {}'.format(req.url)))
        await self.page.goto(self.url + 'redirect1')
        self.assertEqual(events, [
            'GET {}'.format(self.url + 'redirect1'),
            '302 {}'.format(self.url + 'redirect1'),
            'DONE {}'.format(self.url + 'redirect1'),
            'GET {}'.format(self.url + 'redirect2'),
            '200 {}'.format(self.url + 'redirect2'),
            'DONE {}'.format(self.url + 'redirect2'),
        ])
