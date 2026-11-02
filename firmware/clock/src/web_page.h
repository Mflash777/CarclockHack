#pragma once
#include <pgmspace.h>

const char PAGE_HEAD[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>HackClock</title>
<style>
body{font-family:system-ui,sans-serif;background:#111;color:#eee;max-width:520px;margin:auto;padding:16px}
h1{color:#ffa500;margin:.2em 0 .6em}fieldset{border:1px solid #333;border-radius:10px;margin:0 0 14px;padding:10px 14px}
legend{color:#ffa500;padding:0 6px}label{display:block;margin:8px 0;font-size:14px}
input:not([type=checkbox]){display:block;width:100%;box-sizing:border-box;padding:8px;margin-top:4px;
background:#222;color:#fff;border:1px solid #444;border-radius:6px;font-size:16px}
.days label{display:inline-block;margin-right:8px}button{background:#ffa500;color:#111;border:0;border-radius:8px;
padding:10px 18px;font-size:16px;margin-top:6px}a{color:#ffa500}
</style></head><body>)HTML";

const char PAGE_TAIL[] PROGMEM = R"HTML(</body></html>)HTML";
