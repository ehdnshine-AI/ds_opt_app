<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>DS Opt Platform</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 40px;
            line-height: 1.6;
        }
        code {
            background: #f3f4f6;
            padding: 2px 6px;
        }
    </style>
</head>
<body>
    <h1>DS Opt Platform</h1>
    <p>Tomcat front page is running.</p>
    <p>FastAPI endpoints are exposed through nginx.</p>
    <ul>
        <li><a href="/docs">API Docs</a></li>
        <li><a href="/healthz">API Health</a></li>
        <li><code>/api/solve</code></li>
    </ul>
</body>
</html>
