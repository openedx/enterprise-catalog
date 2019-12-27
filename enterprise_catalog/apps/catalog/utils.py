# -*- coding: utf-8 -*-
"""
Utility functions for catalog app.
"""
from __future__ import absolute_import, division, unicode_literals

import hashlib
import json


def get_content_filter_hash(content_filter):
    content_filter_sorted_keys = json.dumps(content_filter, sort_keys=True).encode()
    content_filter_hash = hashlib.md5(content_filter_sorted_keys).hexdigest()
    return content_filter_hash
