from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# 系统相关操作，例如创建文件夹、路径处理
import os

# 正则表达式，用于文本匹配和清理文件名
import re

# JSON数据处理，用于保存和读取下载进度
import json

# HTML实体解析，例如处理 &nbsp; 等特殊字符
import html

# 字符编码处理，用于解析微信读书返回的编码内容
import codecs

# 随机等待时间，降低请求频率
import random

# 时间控制，例如程序暂停
import time


# Chrome浏览器用户数据目录
# 使用已有Chrome登录状态，避免每次重新扫码登录
PROFILE_DIR = "/Users/xxx/Desktop/wechat_chrome_profile"


# 微信读书公众号对应的bookId
# 不同公众号对应不同ID
BOOK_ID = "MP_WXS_xxxxxxxxxx"


# 文章输出目录
# 下载后的Markdown文件会保存到这里
OUTPUT_DIR = "xxx全部文章"


# 保存程序运行进度的文件
# 例如已经下载到offset=200，下次运行可以继续
PROGRESS_FILE = os.path.join(
    OUTPUT_DIR,
    "progress.json"
)


# 如果输出目录不存在，则自动创建
os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


def load_progress():

    """
    读取上一次运行保存的下载进度

    返回：
        offset:
        当前已经处理到微信读书接口的哪个位置
    """

    # 如果进度文件不存在，说明第一次运行
    if not os.path.exists(PROGRESS_FILE):
        return 0

    try:

        # 打开进度文件
        with open(
            PROGRESS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            # 读取JSON内容
            data = json.load(f)

        # 获取offset字段
        # 如果不存在，则默认从0开始
        return data.get("offset", 0)

    except:

        # 如果文件损坏，重新从0开始
        return 0



def save_progress(offset):

    """
    保存当前下载进度

    参数：
        offset:
        当前已经处理的位置
    """

    with open(
        PROGRESS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "offset": offset
            },
            f,

            # 保持中文可读
            ensure_ascii=False,

            # JSON格式化缩进
            indent=2
        )



def safe_name(name):

    """
    清理文件名中的非法字符

    Windows和部分系统不允许以下字符出现在文件名中：
    \\ / : * ? " < > |

    替换成下划线，避免保存文件失败
    """

    return re.sub(
        r'[\\/:*?"<>|]',
        "_",
        name
    )



def extract_field(text, field_name):

    """
    从微信读书返回的HTML文本中
    提取指定字段内容

    例如：
    title: '文章标题'

    提取：
    文章标题
    """

    pattern = rf"{field_name}\s*:\s*'([^']*)'"

    m = re.search(
        pattern,
        text
    )

    if m:

        return m.group(1)

    return ""



def get_articles(page, offset):

    """
    获取公众号文章列表

    参数：
        page:
        Playwright页面对象

        offset:
        微信读书接口分页位置

    返回：
        [
            {
                "title": "文章标题",
                "reviewId": "文章ID"
            }
        ]

    """

    # 微信读书公众号文章列表接口
    # offset用于分页读取
    api_url = (
        "https://weread.qq.com/web/mp/articles"
        f"?bookId={BOOK_ID}"
        f"&offset={offset}"
    )


    # 访问接口
    page.goto(api_url)


    # 等待接口响应
    page.wait_for_timeout(3000)


    # 获取页面返回文本
    text = page.locator("body").inner_text()


    # 如果登录状态失效
    if "登录超时" in text:

        return "LOGIN_TIMEOUT"


    try:

        # 微信接口返回JSON格式数据
        data = json.loads(text)


    except Exception as e:

        print("JSON解析失败")
        print(e)

        return []



    # 获取reviews列表
    reviews = data.get(
        "reviews",
        []
    )


    result = []


    # 遍历文章分组
    for review_group in reviews:


        # 每个分组里面包含具体文章
        subs = review_group.get(
            "subReviews",
            []
        )


        # 遍历具体文章
        for item in subs:


            # 获取文章唯一ID
            review_id = item["reviewId"]


            # 获取文章标题
            title = (
                item["review"]
                ["mpInfo"]
                ["title"]
            )


            result.append(
                {
                    "title": title,
                    "reviewId": review_id
                }
            )


    return result


def save_article(page, article):

    """
    下载并保存单篇文章

    参数：
        page:
        Playwright页面对象

        article:
        包含文章标题和reviewId的信息

    返回：
        True:
            保存成功或文章已经存在

        False:
            保存失败
    """


    # 获取文章唯一ID
    review_id = article["reviewId"]


    # 微信读书文章正文接口
    url = (
        "https://weread.qq.com/web/mp/content"
        f"?reviewId={review_id}"
    )


    print()
    print("抓取:")
    print(article["title"])


    # 打开文章详情页面
    page.goto(url)


    # 随机等待8-12秒
    # 模拟正常浏览行为，同时等待页面内容加载
    page.wait_for_timeout(
        random.randint(
            8000,
            12000
        )
    )


    # 获取当前页面完整HTML源码
    html_text = page.content()


    # 如果HTML中不存在正文字段
    # 说明文章正文获取失败
    if "content_noencode" not in html_text:

        print("正文不存在")

        return False



    # 提取文章标题
    title = extract_field(
        html_text,
        "title"
    )


    # 提取文章发布时间
    create_time = extract_field(
        html_text,
        "create_time"
    )



    # 微信读书返回的正文内容字段标识
    start_key = "content_noencode: '"


    # 查找正文开始位置
    start = html_text.find(start_key)


    if start == -1:

        print("content_noencode没找到")

        return False



    # 跳过字段名称，只保留正文内容
    start += len(start_key)



    # 正文结束位置
    # 微信返回数据中，正文后面紧跟create_time字段
    end = html_text.find(
        "create_time:",
        start
    )


    if end == -1:

        print("create_time没找到")

        return False



    # 截取原始正文字符串
    content_raw = html_text[start:end]



    # 去掉结尾多余字符
    content_raw = re.sub(
        r"',\s*$",
        "",
        content_raw,
        flags=re.S
    )



    try:

        # 微信读书返回的正文经过unicode编码
        # 这里进行第一次解码
        content_html = codecs.decode(
            content_raw,
            "unicode_escape"
        )


        # 处理HTML实体字符
        # 例如：
        # &amp; 转换为 &
        content_html = html.unescape(
            content_html
        )



        try:

            # 处理部分中文乱码问题
            content_html = (
                content_html
                .encode("latin1")
                .decode("utf-8")
            )


        except:

            # 如果已经是正常编码
            # 则跳过转换
            pass



    except Exception as e:


        print("解码失败")
        print(e)

        return False



    # 使用BeautifulSoup解析HTML正文
    soup = BeautifulSoup(
        content_html,
        "html.parser"
    )



    # 提取纯文本内容
    # 用换行符替代HTML标签
    text = soup.get_text("\n")



    lines = []



    # 清理空行
    for line in text.splitlines():

        line = line.strip()


        if line:

            lines.append(line)



    # 重新组合文章正文
    # 每段之间增加空行，提高Markdown阅读体验
    text = "\n\n".join(lines)



    # 生成Markdown格式文章
    md = f"""# {title}

时间：{create_time}

---

{text}
"""



    # 根据标题生成文件路径
    filename = os.path.join(
        OUTPUT_DIR,
        safe_name(title) + ".md"
    )



    # 如果文章已经存在
    # 避免重复下载
    if os.path.exists(filename):

        print("已存在，跳过")

        return True



    # 保存Markdown文件
    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(md)



    print("保存成功")


    return True


# 使用Playwright启动浏览器自动化环境
with sync_playwright() as p:


    # 启动Chrome持久化上下文
    #
    # persistent_context的特点：
    # 会保存浏览器用户数据
    # 包括登录状态、Cookie等信息
    #
    # 这样下一次运行时无需重复扫码登录
    browser = p.chromium.launch_persistent_context(

        # Chrome用户数据目录
        user_data_dir=PROFILE_DIR,


        # 指定使用本地Chrome浏览器
        channel="chrome",


        # 显示浏览器窗口
        # 设置为False则为无界面运行
        headless=False,


        # 禁用Playwright自动化特征
        # 降低被网站识别为自动化程序的概率
        args=[
            "--disable-blink-features=AutomationControlled"
        ]
    )



    # 创建新的浏览器页面
    page = browser.new_page()



    print("打开微信读书首页")



    # 打开微信读书首页
    page.goto(
        "https://weread.qq.com/"
    )



    # 等待用户确认登录完成
    #
    # 第一次运行时：
    # 用户需要在浏览器中完成微信登录
    #
    # 登录完成后按回车继续执行
    input(
        "确认已经登录后按回车..."
    )



    # 读取之前保存的下载进度
    #
    # 如果之前下载到一半退出，
    # 可以从上次位置继续
    offset = load_progress()



    # 测试时可以手动指定开始位置
    #
    # 例如：
    # offset = 240
    #
    # 正式运行时注释掉
    #offset = 240



    print()

    print(
        "从 offset 开始:",
        offset
    )



    # 无限循环获取文章
    while True:



        print()

        print(
            "=" * 60
        )


        print(
            "读取 offset:",
            offset
        )



        # 获取当前分页的文章列表
        articles = get_articles(
            page,
            offset
        )



        # 如果登录过期
        if articles == "LOGIN_TIMEOUT":


            print()

            print("登录超时")

            print("请重新登录微信读书")


            # 等待用户重新登录
            input(
                "登录后按回车继续..."
            )


            # 登录恢复后继续循环
            continue




        # 如果没有获取到文章
        # 说明已经读取完成
        if not articles:


            print()

            print(
                "没有更多文章"
            )


            break




        # 遍历当前页所有文章
        for article in articles:


            try:


                # 下载单篇文章
                save_article(
                    page,
                    article
                )



            except Exception as e:


                # 捕获单篇文章异常
                #
                # 防止某篇文章失败导致整个程序退出
                print()

                print("异常:")

                print(e)




        # 微信读书接口每次偏移20篇文章
        offset += 20




        # 保存当前进度
        #
        # 即使程序中途关闭，
        # 下次也可以继续下载
        save_progress(offset)



        print()

        print(
            "已记录进度:",
            offset
        )



        # 随机等待5-10秒
        #
        # 避免连续快速请求
        time.sleep(
            random.randint(
                5,
                10
            )
        )




    print()

    print("全部完成")



    # 关闭浏览器
    browser.close()
