# CPA Control Center

تطبيق سطح مكتب احترافي لإدارة أتمتة CPA والبروكسيات. الواجهة مبنية بـ **Node.js + React + Vite**، ومحرك الخدمات المحلي مبني بـ **Python**.

## المزايا
- لوحة تحكم RTL احترافية مع مؤشرات مباشرة وسجل نشاط.
- محرك بروكسي محلي بقراءة قائمة `host:port` أو `scheme://host:port`.
- فحص متوازٍ للبروكسيات مع قياس latency، حالات health، ترتيب ذكي، و circuit-breaker cooldown بعد الإخفاقات المتكررة.
- إعدادات rotation و timeout و retries.
- عزل Electron و `contextIsolation` مفعّل؛ لا يتم إرسال البيانات لخادم خارجي.
- واجهة جاهزة للربط مع محرك الأتمتة والمتصفح المعزول.

## التشغيل
```bash
npm install
# نافذة التطوير (واجهة + API Python)
npm run start
# تشغيل Electron بعد بدء Vite و API
VITE_DEV_SERVER_URL=http://localhost:5173 npm run electron
```

للتجميع:
```bash
npm run build
npm run package
```

> يتطلب Python 3.9 أو أحدث. بروتوكول HTTP/HTTPS مدعوم مباشرة. دعم SOCKS5 يحتاج إضافة PySocks اختيارية، ويُرفض بأمان بدلاً من تمرير اتصال غير مدعوم.

## API المحلي
- `GET /api/state` الحالة الكاملة
- `POST /api/proxies/import` `{ "text": "host:port" }`
- `POST /api/proxies/check` فحص متوازٍ
- `POST /api/proxies/clear`
- `POST /api/automation/toggle`
- `POST /api/settings` لتحديث الإعدادات
