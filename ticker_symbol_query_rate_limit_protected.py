import requests
import pandas as pd
import json
import os
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session():
    """创建一个带有重试策略的会话"""
    session = requests.Session()

    # 设置重试策略
    retry_strategy = Retry(
        total=5,  # 增加重试次数
        backoff_factor=2,  # 增加退避因子
        status_forcelist=[429, 500, 502, 503, 504],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 设置User-Agent
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    return session


def query_wikidata(symbol, session, max_retries=5, base_delay=5):
    """查询Wikidata并处理错误"""

    # 定义端点URL
    endpoint_url = "https://query.wikidata.org/sparql"

    # 定义三个独立的SPARQL查询
    query_1 = """
    SELECT ?ticker ?id
        (GROUP_CONCAT(DISTINCT ?idLabel;separator="| | |") AS ?idLabels)
        (GROUP_CONCAT(DISTINCT ?altLabel; separator = "| | |") AS ?aliases)
        (GROUP_CONCAT(DISTINCT ?industryLabel; separator = "| | |") AS ?industries)
        (GROUP_CONCAT(DISTINCT ?countryLabel; separator = "| | |") AS ?countries)
        (GROUP_CONCAT(DISTINCT ?productLabel; separator = "| | |") AS ?products)
    WHERE {
        {
            # Find the exchange and its ticker
            ?id wdt:P414 ?exchange .
            ?id p:P414 ?exchangesub .
            ?exchangesub pq:P249 ?ticker . FILTER(UCASE(STR(?ticker)) = '""" + symbol + """') .
            OPTIONAL { ?id rdfs:label ?idLabel . FILTER (LANG(?idLabel) = "en") }
        }
        OPTIONAL {
            ?id skos:altLabel ?altLabel .
            FILTER (LANG(?altLabel) = "en")
        }
        OPTIONAL {
            ?id wdt:P452 ?industry .
            ?industry rdfs:label ?industryLabel .
            FILTER (LANG(?industryLabel) = "en")
        }
        OPTIONAL {
            ?id wdt:P17 ?country .
            ?country rdfs:label ?countryLabel .
            FILTER (LANG(?countryLabel) = "en")
        }
        OPTIONAL {
            ?id wdt:P1056 ?product .
            ?product rdfs:label ?productLabel .
            FILTER (LANG(?productLabel) = "en")
        }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
    }
    GROUP BY ?ticker ?id
    """

    query_2 = """
    SELECT ?ticker ?id
        (GROUP_CONCAT(DISTINCT ?idLabel;separator="| | |") AS ?idLabels)
        (GROUP_CONCAT(DISTINCT CONCAT(?subsidiaryLabel, 
            IF(BOUND(?start_time), CONCAT(" (Start: ", STR(?start_time), ")"), ""), 
            IF(BOUND(?end_time), CONCAT(" (End: ", STR(?end_time), ")"), "")
        );separator="| | |") AS ?subsidiaries)
        (GROUP_CONCAT(DISTINCT CONCAT(?ownerOfLabel, 
            IF(BOUND(?start_time_owner), CONCAT(" (Start: ", STR(?start_time_owner), ")"), ""), 
            IF(BOUND(?end_time_owner), CONCAT(" (End: ", STR(?end_time_owner), ")"), "")
        );separator="| | |") AS ?ownedEntities)
    WHERE {
        {
            # Find the exchange and its ticker 
            ?id wdt:P414 ?exchange . 
            ?id p:P414 ?exchangesub .
            ?exchangesub pq:P249 ?ticker . FILTER(UCASE(STR(?ticker)) = '""" + symbol + """') .
            OPTIONAL { ?id rdfs:label ?idLabel . FILTER (LANG(?idLabel) = "en") }
        }
        OPTIONAL {
            ?id wdt:P355 ?subsidiary .
            ?subsidiary rdfs:label ?subsidiaryLabel .
            FILTER (LANG(?subsidiaryLabel) = "en")
            OPTIONAL { ?id p:P355 [ps:P355 ?subsidiary; pq:P580 ?start_time; pq:P582 ?end_time] }
        }
        OPTIONAL {
            ?id wdt:P1830 ?ownerOf .
            ?ownerOf rdfs:label ?ownerOfLabel .
            FILTER (LANG(?ownerOfLabel) = "en")
            OPTIONAL { ?id p:P1830 [ps:P1830 ?ownerOf; pq:P580 ?start_time_owner; pq:P582 ?end_time_owner] }
        }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
    }
    GROUP BY ?ticker ?id
    """

    query_3 = """
    SELECT ?ticker ?id
        (GROUP_CONCAT(DISTINCT ?ceoLabel;separator="| | |") AS ?ceos)
        (GROUP_CONCAT(DISTINCT CONCAT(?ceoLabel, 
            IF(BOUND(?ceoStart), CONCAT(" (Start: ", STR(?ceoStart), ")"), ""), 
            IF(BOUND(?ceoEnd), CONCAT(" (End: ", STR(?ceoEnd), ")"), "")
        );separator="| | |") AS ?ceosWithTerms)
        (GROUP_CONCAT(DISTINCT ?boardMemberLabel;separator="| | |") AS ?boardMembers)
        (GROUP_CONCAT(DISTINCT CONCAT(?boardMemberLabel, 
            IF(BOUND(?boardMemberStart), CONCAT(" (Start: ", STR(?boardMemberStart), ")"), ""), 
            IF(BOUND(?boardMemberEnd), CONCAT(" (End: ", STR(?boardMemberEnd), ")"), "")
        );separator="| | |") AS ?boardMembersWithTerms)
        (GROUP_CONCAT(DISTINCT CONCAT(?legalFormLabel, 
            IF(BOUND(?legalFormStart), CONCAT(" (Start: ", STR(?legalFormStart), ")"), ""), 
            IF(BOUND(?legalFormEnd), CONCAT(" (End: ", STR(?legalFormEnd), ")"), "")
        );separator="| | |") AS ?legalFormsWithDates)
        (SAMPLE(?shortName) AS ?shortNames)
    WHERE {
        {
            # Find the exchange and its ticker 
            ?id wdt:P414 ?exchange . 
            ?id p:P414 ?exchangesub .
            ?exchangesub pq:P249 ?ticker . FILTER(UCASE(STR(?ticker)) = '""" + symbol + """') .
        }
        OPTIONAL {
            ?id p:P169 ?ceoStatement .
            ?ceoStatement ps:P169 ?ceo .
            ?ceo rdfs:label ?ceoLabel .
            FILTER (LANG(?ceoLabel) = "en")
            OPTIONAL { ?ceoStatement pq:P580 ?ceoStart }
            OPTIONAL { ?ceoStatement pq:P582 ?ceoEnd }
        }
        OPTIONAL {
            ?id p:P3320 ?boardMemberStatement .
            ?boardMemberStatement ps:P3320 ?boardMember .
            ?boardMember rdfs:label ?boardMemberLabel .
            FILTER (LANG(?boardMemberLabel) = "en")
            OPTIONAL { ?boardMemberStatement pq:P580 ?boardMemberStart }
            OPTIONAL { ?boardMemberStatement pq:P582 ?boardMemberEnd }
        }
        OPTIONAL {
            ?id wdt:P1454 ?legalForm .
            ?legalForm rdfs:label ?legalFormLabel .
            FILTER (LANG(?legalFormLabel) = "en")
            OPTIONAL {
                ?id p:P1454 ?legalFormStatement .
                ?legalFormStatement ps:P1454 ?legalForm .
                OPTIONAL { ?legalFormStatement pq:P580 ?legalFormStart }
                OPTIONAL { ?legalFormStatement pq:P582 ?legalFormEnd }
            }
        }
        OPTIONAL {
            ?id wdt:P1813 ?shortName .
            FILTER (LANG(?shortName) = "en")
        }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
    }
    GROUP BY ?ticker ?id
    """

    for attempt in range(max_retries):
        try:
            print(f"查询 {symbol} (尝试 {attempt + 1}/{max_retries})")

            # 发送三个独立的请求
            response_1 = session.get(
                endpoint_url,
                params={'query': query_1, 'format': 'json'},
                timeout=(15, 60)
            )

            # 在请求之间添加短暂延迟
            time.sleep(random.uniform(1, 3))

            response_2 = session.get(
                endpoint_url,
                params={'query': query_2, 'format': 'json'},
                timeout=(15, 60)
            )

            time.sleep(random.uniform(1, 3))

            response_3 = session.get(
                endpoint_url,
                params={'query': query_3, 'format': 'json'},
                timeout=(15, 60)
            )

            if response_1.ok and response_2.ok and response_3.ok:
                # 处理三个查询的结果
                data_1 = response_1.json()
                data_2 = response_2.json()
                data_3 = response_3.json()

                all_results = []

                # 假设所有查询返回相同数量的结果行
                max_results = max(
                    len(data_1['results']['bindings']),
                    len(data_2['results']['bindings']),
                    len(data_3['results']['bindings'])
                )

                for i in range(max_results):
                    # 安全地获取每个查询的结果
                    result_1 = data_1['results']['bindings'][i] if i < len(data_1['results']['bindings']) else {}
                    result_2 = data_2['results']['bindings'][i] if i < len(data_2['results']['bindings']) else {}
                    result_3 = data_3['results']['bindings'][i] if i < len(data_3['results']['bindings']) else {}

                    entry = {
                        'id_label': result_1.get('idLabels', {}).get('value', ''),
                        'ticker': result_1.get('ticker', {}).get('value', symbol),
                        'country': result_1.get('countries', {}).get('value', '').split('| | |') if result_1.get(
                            'countries', {}).get('value') else [],
                        'industry': result_1.get('industries', {}).get('value', '').split('| | |') if result_1.get(
                            'industries', {}).get('value') else [],
                        'aliases': result_1.get('aliases', {}).get('value', '').split('| | |') if result_1.get(
                            'aliases', {}).get('value') else [],
                        'products': result_1.get('products', {}).get('value', '').split('| | |') if result_1.get(
                            'products', {}).get('value') else [],
                        'subsidiaries': result_2.get('subsidiaries', {}).get('value', '').split(
                            '| | |') if result_2.get('subsidiaries', {}).get('value') else [],
                        'owned_entities': result_2.get('ownedEntities', {}).get('value', '').split(
                            '| | |') if result_2.get('ownedEntities', {}).get('value') else [],
                        'ceos': result_3.get('ceosWithTerms', {}).get('value', '').split('| | |') if result_3.get(
                            'ceosWithTerms', {}).get('value') else [],
                        'board_members': result_3.get('boardMembersWithTerms', {}).get('value', '').split(
                            '| | |') if result_3.get('boardMembersWithTerms', {}).get('value') else [],
                    }

                    # 清理空字符串
                    entry['country'] = [c for c in entry['country'] if c.strip()]
                    entry['industry'] = [i for i in entry['industry'] if i.strip()]
                    entry['aliases'] = [a for a in entry['aliases'] if a.strip()]
                    entry['products'] = [p for p in entry['products'] if p.strip()]
                    entry['subsidiaries'] = [s for s in entry['subsidiaries'] if s.strip()]
                    entry['owned_entities'] = [o for o in entry['owned_entities'] if o.strip()]
                    entry['ceos'] = [c for c in entry['ceos'] if c.strip()]
                    entry['board_members'] = [b for b in entry['board_members'] if b.strip()]

                    all_results.append(entry)

                # 如果没有结果，创建一个空的条目
                if not all_results:
                    all_results.append({
                        'id_label': '',
                        'ticker': symbol,
                        'country': [],
                        'industry': [],
                        'aliases': [],
                        'products': [],
                        'subsidiaries': [],
                        'owned_entities': [],
                        'ceos': [],
                        'board_members': [],
                    })

                # 确保目录存在
                os.makedirs('info/Icahn', exist_ok=True)

                # 创建并写入JSON
                file_path = os.path.join('info', 'Icahn', f'{symbol}_info.json')
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(all_results, f, indent=4, ensure_ascii=False)

                print(f"成功保存 {symbol} 的信息")

                # 成功后添加随机延迟
                delay = random.uniform(5, 10)  # 增加延迟时间
                print(f"等待 {delay:.1f} 秒...")
                time.sleep(delay)
                return True

            else:
                # 检查哪个请求失败了
                failed_responses = []
                if not response_1.ok:
                    failed_responses.append(f"Query 1: {response_1.status_code}")
                if not response_2.ok:
                    failed_responses.append(f"Query 2: {response_2.status_code}")
                if not response_3.ok:
                    failed_responses.append(f"Query 3: {response_3.status_code}")

                print(f"请求失败: {', '.join(failed_responses)}")

                # 特别处理429错误
                if any(r.status_code == 429 for r in [response_1, response_2, response_3]):
                    print(f"遇到429错误 - 请求过于频繁")
                    if attempt < max_retries - 1:
                        wait_time = base_delay * (3 ** attempt) + random.uniform(10, 20)
                        print(f"等待 {wait_time:.1f} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        print(f"达到最大重试次数，跳过 {symbol}")
                        return False
                else:
                    if attempt < max_retries - 1:
                        wait_time = base_delay * (2 ** attempt) + random.uniform(2, 8)
                        print(f"等待 {wait_time:.1f} 秒后重试...")
                        time.sleep(wait_time)

        except requests.exceptions.RequestException as e:
            print(f"请求异常: {e}")
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt) + random.uniform(5, 15)
                print(f"等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"达到最大重试次数，跳过 {symbol}")
                return False

        except Exception as e:
            print(f"未知错误: {e}")
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt) + random.uniform(5, 15)
                print(f"等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"达到最大重试次数，跳过 {symbol}")
                return False

    return False


def load_progress():
    """加载进度记录"""
    progress_file = 'progress.json'
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
    return {'processed': [], 'failed': []}


def save_progress(progress):
    """保存进度记录"""
    progress_file = 'progress.json'
    with open(progress_file, 'w') as f:
        json.dump(progress, f, indent=2)


def main():
    # 创建会话
    session = create_session()

    # 读取CSV文件
    try:
        ticker_df = pd.read_csv("Icahn_all_quarters_merged_with_tickers.csv")
    except FileNotFoundError:
        print("CSV文件未找到，请确认文件路径")
        return

    # 加载进度
    progress = load_progress()
    processed_symbols = set(progress.get('processed', []))
    failed_symbols = set(progress.get('failed', []))

    successful_queries = len(processed_symbols)
    failed_queries = len(failed_symbols)

    print(f"已处理: {successful_queries}, 已失败: {failed_queries}")
    print(f"总共需要处理: {len(ticker_df)}")

    for index, row in ticker_df.iterrows():
        symbol = str(row['Symbol']).strip().upper()

        # 检查文件是否实际存在
        file_path = os.path.join('info', 'ticker2', f'{symbol}_info.json')
        file_exists = os.path.exists(file_path)

        # 跳过已经处理过且文件存在的
        if symbol in processed_symbols and file_exists:
            print(f"跳过已处理的: {symbol} ({index + 1}/{len(ticker_df)})")
            continue

        # 如果在processed_symbols中但文件不存在，从processed_symbols中移除
        if symbol in processed_symbols and not file_exists:
            print(f"文件不存在，重新处理: {symbol} ({index + 1}/{len(ticker_df)})")
            processed_symbols.discard(symbol)

        # 跳过已经失败过的（可选择重试失败的）
        if symbol in failed_symbols:
            print(f"重试之前失败的: {symbol} ({index + 1}/{len(ticker_df)})")

        print(f"\n当前处理: {symbol} ({index + 1}/{len(ticker_df)})")

        if query_wikidata(symbol, session):
            successful_queries += 1
            processed_symbols.add(symbol)
            if symbol in failed_symbols:
                failed_symbols.remove(symbol)
        else:
            failed_queries += 1
            failed_symbols.add(symbol)

        # 更新并保存进度
        progress = {
            'processed': list(processed_symbols),
            'failed': list(failed_symbols)
        }
        save_progress(progress)

        # 每3个请求后额外休息（减少频率以适应三个查询）
        if (index + 1) % 3 == 0:
            extra_wait = random.uniform(15, 25)
            print(f"已处理3个请求，额外休息 {extra_wait:.1f} 秒...")
            time.sleep(extra_wait)

        # 每10个请求后更长休息（调整频率）
        if (index + 1) % 10 == 0:
            long_wait = random.uniform(60, 120)
            print(f"已处理10个请求，长时间休息 {long_wait:.1f} 秒...")
            time.sleep(long_wait)

    print(f"\n处理完成!")
    print(f"成功: {successful_queries}")
    print(f"失败: {failed_queries}")

    if failed_symbols:
        print(f"失败的股票代码: {', '.join(failed_symbols)}")


if __name__ == "__main__":
    main()