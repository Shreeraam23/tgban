import aiohttp, random, asyncio, re, os
from aiohttp_socks import ProxyConnector
from faker import Faker
from tqdm import tqdm
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler


TOKEN = "8071095750:AAGZfMeDl69RdlCVrWZ6sA661pNwChkcxRc"  

fake = Faker()
USERNAME, = range(1)

# Global proxy list that gets updated every second
current_proxies = []
proxy_refresh_task = None


def load_reports():
    with open("report.txt", "r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]


async def is_valid_username(username):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://t.me/{username}", timeout=aiohttp.ClientTimeout(total=5)) as response:
                text = await response.text()
                return "tgme_page_title" in text
    except:
        return False


def generate_data(username, message):
    name = fake.name()
    email = fake.email().split("@")[0] + "@" + random.choice(["gmail.com", "yahoo.com", "outlook.com", "rediffmail.com"])
    number = '7' + ''.join([str(random.randint(0, 9)) for _ in range(9)])
    final_msg = message.replace("@username", f"@{username}")
    return {
        "message": final_msg,
        "legal_name": name,
        "email": email,
        "phone": number,
        "setln": ""
    }, name, email, number, final_msg


def validate_proxy(proxy_line):
    """Validate and format proxy entry"""
    proxy_line = proxy_line.strip()
    if not proxy_line or ':' not in proxy_line:
        return None
    
    # If already has scheme, validate it
    if '://' in proxy_line:
        if proxy_line.startswith(('socks4://', 'socks5://', 'http://')):
            return proxy_line
        return None
    
    # Add default socks4 scheme
    parts = proxy_line.split(':')
    if len(parts) == 2:
        try:
            port = int(parts[1])
            if 1 <= port <= 65535:
                return f"socks4://{proxy_line}"
        except ValueError:
            pass
    return None


async def fetch_from_single_source(session, source_url, proxy_type):
    """Fetch proxies from a single source quickly"""
    try:
        source_name = source_url.split('/')[-1]
        async with session.get(source_url, timeout=aiohttp.ClientTimeout(total=3)) as response:
            if response.status == 200:
                text = await response.text()
                raw_proxies = [line.strip() for line in text.split('\n') if line.strip() and ':' in line]
                
                formatted_proxies = []
                for proxy in raw_proxies[:50]:  # Take 50 from each source
                    if '://' in proxy:
                        formatted_proxies.append(proxy)
                    else:
                        formatted_proxy = f"{proxy_type}://{proxy}"
                        if validate_proxy(formatted_proxy):
                            formatted_proxies.append(formatted_proxy)
                
                return formatted_proxies
    except Exception as e:
        pass
    return []

async def fast_test_proxy(proxy):
    """Super fast proxy testing with 2 second timeout"""
    try:
        if proxy.startswith('http://'):
            # For HTTP proxies, use aiohttp proxy parameter
            async with aiohttp.ClientSession() as session:
                async with session.get("http://httpbin.org/ip", proxy=proxy, timeout=aiohttp.ClientTimeout(total=2)) as response:
                    return response.status == 200
        else:
            # For SOCKS proxies, use ProxyConnector
            connector = ProxyConnector.from_url(proxy)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get("http://httpbin.org/ip", timeout=aiohttp.ClientTimeout(total=2)) as response:
                    return response.status == 200
    except:
        return False

async def continuous_proxy_refresh():
    """TRUE every-second proxy fetching and testing as requested"""
    global current_proxies
    
    # All proxy sources - split into small batches for every-second fetching
    all_sources = [
        ("https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt", "http"),
        ("https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks4/data.txt", "socks4"),
        ("https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt", "socks5"),
        ("https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all", "http"),
        ("https://api.proxyscrape.com/v2/?request=get&protocol=socks4&timeout=10000&country=all", "socks4"),
        ("https://api.proxyscrape.com/v2/?request=get&protocol=socks5&timeout=10000&country=all", "socks5"),
        ("https://www.proxy-list.download/api/v1/get?type=http", "http"),
        ("https://www.proxy-list.download/api/v1/get?type=socks4", "socks4"),
        ("https://www.proxy-list.download/api/v1/get?type=socks5", "socks5"),
        ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", "http"),
        ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt", "socks4"),
        ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "socks5"),
        ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "http"),
        ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt", "socks4"),
        ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "socks5"),
        ("https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt", "http"),
        ("https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt", "socks4"),
        ("https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt", "socks5"),
        ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt", "http"),
        ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt", "socks4"),
        ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt", "socks5")
    ]
    
    source_index = 0
    proxy_pool = set()
    
    print("ðŸš€ Starting REAL-TIME proxy system - fetching new proxies every second!")
    
    while True:
        try:
            # Fetch from 3-4 sources simultaneously every second
            current_sources = []
            for i in range(4):  # Take 4 sources per second
                if source_index < len(all_sources):
                    current_sources.append(all_sources[source_index])
                    source_index += 1
                else:
                    source_index = 0  # Reset to beginning
                    current_sources.append(all_sources[source_index])
                    source_index += 1
            
            # Fetch from multiple sources in parallel
            async with aiohttp.ClientSession() as session:
                fetch_tasks = [fetch_from_single_source(session, url, ptype) for url, ptype in current_sources]
                source_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                
                # Collect new proxies
                new_proxies = []
                for result in source_results:
                    if isinstance(result, list):
                        new_proxies.extend(result)
                
                # Add to proxy pool (remove duplicates)
                for proxy in new_proxies:
                    proxy_pool.add(proxy)
                
                # Test a batch of new proxies every second
                if new_proxies:
                    # Test 50 proxies simultaneously with fast testing
                    test_batch = list(new_proxies)[:50]
                    test_tasks = [fast_test_proxy(proxy) for proxy in test_batch]
                    test_results = await asyncio.gather(*test_tasks, return_exceptions=True)
                    
                    # Update working proxy list
                    new_working = []
                    for proxy, is_working in zip(test_batch, test_results):
                        if is_working is True:
                            new_working.append(proxy)
                    
                    if new_working:
                        # Add new working proxies to current list
                        current_proxies.extend(new_working)
                        # Keep only last 1000 to prevent memory issues
                        current_proxies = current_proxies[-1000:]
                        print(f"âš¡ Added {len(new_working)} working proxies! Total: {len(current_proxies)}")
                    
                print(f"ðŸ”„ Pool: {len(proxy_pool)} | Working: {len(current_proxies)} | Tested {len(test_batch) if new_proxies else 0} new")
                
        except Exception as e:
            print(f"âŒ Real-time refresh error: {str(e)[:50]}")
        
        # Wait exactly 1 second before next fetch/test cycle
        await asyncio.sleep(1)

async def send_data(data, proxy=None):
    headers = {
        "Host": "telegram.org",
        "origin": "https://telegram.org", 
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "Mozilla/5.0",
        "referer": "https://telegram.org/support"
    }
    try:
        connector = None
        if proxy:
            connector = ProxyConnector.from_url(proxy)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post("https://telegram.org/support", data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as res:
                text = await res.text()
                success = "Thank you" in text or res.status == 200
                if success:
                    print(f"âœ… Report sent via {proxy if proxy else 'direct'}")
                else:
                    print(f"âŒ Report failed via {proxy if proxy else 'direct'} (Status: {res.status})")
                return success, proxy if proxy else "direct"
    except Exception as e:
        print(f"âŒ Send error via {proxy if proxy else 'direct'}: {str(e)[:50]}")
        return False, proxy if proxy else "direct"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ðŸ‘‹ Welcome! Please enter the @username or channel/group you want to report (without @): \nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\nâ”£á´˜ÊŸá´‡á´€êœ±á´‡ á´Šá´ÉªÉ´ á´Ê á´œá´˜á´…á´€á´›á´‡êœ± á´„Êœá´€É´É´á´‡ÊŸ\nâ”£ðƒðžð¯ðžð¥ð¨ð©ðžð« âž¥ @NGYT777GG :")
    return USERNAME


async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global proxy_refresh_task, current_proxies
    
    username = update.message.text.strip().lstrip('@')
    context.user_data["username"] = username

    if not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
        await update.message.reply_text("âŒ Invalid username format.")
        return ConversationHandler.END

    await update.message.reply_text("ðŸ” Checking if the username exists...")
    if not await is_valid_username(username):
        await update.message.reply_text("âŒ Username not available on Telegram.")
        return ConversationHandler.END

    await update.message.reply_text("âœ… Username is valid. Starting report process...")

    # Start continuous proxy refresh if not already running
    if proxy_refresh_task is None or proxy_refresh_task.done():
        await update.message.reply_text("ðŸ”„ Starting continuous proxy refresh system...")
        proxy_refresh_task = asyncio.create_task(continuous_proxy_refresh())

    # Begin reporting
    reports = load_reports()
    total = 200
    success_count = 0
    progress_message = await update.message.reply_text("ðŸ“¤ Starting reports...")

    report_log = []
    proxy_index = 0
    success_by_proxy = {}
    
    for i, msg in enumerate(reports):
        form_data, name, email, number, final_msg = generate_data(username, msg)
        
        # Use atomic snapshot of current proxies to avoid inconsistency
        local_proxies = current_proxies[:]  # Create snapshot
        proxy = None
        if local_proxies:
            proxy = local_proxies[proxy_index % len(local_proxies)]
            proxy_index += 1
        
        success, used_proxy = await send_data(form_data, proxy)
        
        if success:
            success_count += 1
            success_by_proxy[used_proxy] = success_by_proxy.get(used_proxy, 0) + 1
            report_log.append(f"Report {i+1}:\nName: {name}\nEmail: {email}\nPhone: {number}\nProxy: {used_proxy}\nMessage: {final_msg}\n---\n")
        
        # Sleep for 1 second (matching proxy refresh rate)
        await asyncio.sleep(1) 

        percent = int(((i + 1) / total) * 100)
        progress_bar = "â–ˆ" * (percent // 10) + "â–’" * (10 - (percent // 10))
        proxy_stats = "\n".join(f"ðŸŒ {p}: {c} successful" for p, c in success_by_proxy.items())
        current_proxy_count = len(current_proxies) if current_proxies else 0
        await progress_message.edit_text(f"ðŸ“Š Progress: [{progress_bar}] {percent}%\nðŸ“¤ Sent: {i+1}/{total}\nðŸ”„ Available Proxies: {current_proxy_count}\n\n{proxy_stats}")
        
        if len(report_log) > 0 and len(report_log) % 50 == 0:
     
            with open(f"reports_{username}.txt", "w", encoding="utf-8") as f:
                f.writelines(report_log)
            await update.message.reply_document(
                document=open(f"reports_{username}.txt", "rb"),
                caption=f"ðŸ“‹ Report details for {success_count} reports"
            )
        
        if success_count > 0 and success_count % 50 == 0:
            await update.message.reply_text(f"âœ… Successfully sent {success_count} reports!")

    await progress_message.edit_text(f"âœ… Complete!\nðŸ“Š Progress: [â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆ] 100%\nðŸ“¨ Total successful reports: {success_count}/{total}")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("âŒ Cancelled.")
    return ConversationHandler.END


def main():
    application = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(conv)
    application.run_polling()

if __name__ == "__main__":
    main()
