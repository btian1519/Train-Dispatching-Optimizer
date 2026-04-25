@echo off
chcp 65001 >nul
echo =======================================================
echo   🚄 Train Dispatching Optimizer - 代码自动拉取工具
echo =======================================================
echo.

:: 检查是否安装了 Git
where git >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 你的电脑上好像还没安装 Git！
    echo 请先去这个网址下载：https://git-scm.com/downloads
    echo 下载后一路无脑点击 Next 安装即可。安装完再来双击我！
    echo.
    pause
    exit /b
)

echo [检测通过] Git 已经就绪，开始拉取项目...
echo.
echo -------------------------------------------------------
echo ⚠️  注意：如果等下弹出一个 GitHub 的登录网页或小窗口，
echo ⚠️  请点击 "Sign in with your browser" 授权登录你的账号。
echo -------------------------------------------------------
echo.

:: 使用 HTTPS 方式克隆（对新手最友好，不需要配置 SSH 密钥）
git clone https://github.com/btian1519/Train-Dispatching-Optimizer.git

if %ERRORLEVEL% equ 0 (
    echo.
    echo 🎉 太棒了！代码已经成功下载到当前目录的 Train-Dispatching-Optimizer 文件夹中了。
    echo 赶紧用 VSCode 打开那个文件夹，开始愉快的合作吧！
) else (
    echo.
    echo ❌ 拉取失败了。请检查以下两点：
    echo 1. 你有没有去邮箱里点击 "Accept Invitation" 接受我的 GitHub 邀请？
    echo 2. 刚才如果弹出了登录网页，有没有登录成功？
)

echo.
pause
