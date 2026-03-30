@echo off
echo Fixing SpotEasy repo...

git config core.autocrlf false

git rm --force static\live.js 2>nul
git rm --force static\keep-alive.js 2>nul
git rm --force static\notifications.js 2>nul
git rm --force static\firebase-sw.js 2>nul
git rm --force static\sw.js 2>nul
git rm --force nixpacks.toml 2>nul
git rm --force Dockerfile 2>nul

del static\live.js 2>nul
del static\keep-alive.js 2>nul
del static\notifications.js 2>nul
del static\firebase-sw.js 2>nul
del static\sw.js 2>nul
del nixpacks.toml 2>nul
del Dockerfile 2>nul

echo // keep alive > static\live.js
echo // notifications > static\notifications.js
echo // firebase stub > static\firebase-sw.js

echo var C='spoteasy-v2';self.addEventListener('install',function(e){self.skipWaiting();});self.addEventListener('activate',function(e){self.clients.claim();});self.addEventListener('fetch',function(e){if(e.request.method!=='GET')return;e.respondWith(fetch(e.request).catch(function(){return caches.match(e.request);}));});> static\sw.js

git add .
git commit -m "fix: clean all static files no Dockerfile"
git push

echo DONE! Check Railway now.
pause
