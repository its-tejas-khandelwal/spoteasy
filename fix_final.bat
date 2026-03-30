@echo off
echo === SpotEasy Final Fix ===

cd C:\Users\Tejas\Desktop\spoteasy

git config core.autocrlf false

echo * text=auto eol=lf > .gitattributes
echo *.py text eol=lf >> .gitattributes
echo *.html text eol=lf >> .gitattributes
echo *.js text eol=lf >> .gitattributes
echo *.json text eol=lf >> .gitattributes
echo *.txt text eol=lf >> .gitattributes
echo *.md text eol=lf >> .gitattributes
echo *.toml text eol=lf >> .gitattributes
echo *.png binary >> .gitattributes
echo *.jpg binary >> .gitattributes

git rm --force live.js 2>nul
git rm --force static\live.js 2>nul
git rm --force notifications.js 2>nul
git rm --force keep-alive.js 2>nul
git rm --force firebase-sw.js 2>nul
git rm --force Dockerfile 2>nul
git rm --force nixpacks.toml 2>nul

del live.js 2>nul
del notifications.js 2>nul
del keep-alive.js 2>nul
del firebase-sw.js 2>nul
del Dockerfile 2>nul
del nixpacks.toml 2>nul
del static\live.js 2>nul
del static\keep-alive.js 2>nul
del static\notifications.js 2>nul
del static\firebase-sw.js 2>nul

git rm -r --cached . >nul 2>nul
git add .
git commit -m "fix: gitattributes LF endings, remove all corrupted files"
git push

echo === DONE! Check Railway now ===
pause
