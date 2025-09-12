import json
import os
import pandas as pd
from rapidfuzz import fuzz
from dateutil import parser

from dateutil.tz import tzutc
from tqdm import tqdm

import multiprocessing as mp
import numpy as np

import re


# Function to check if the date of the article is within the start and end date of a CEO or board member
def is_within_period(article_date, start_date, end_date):
    # 如果文章日期为None，返回False（无法确定是否在期间内）
    if article_date is None:
        return False

    # Convert all datetimes to aware datetimes in UTC for comparison
    if article_date and article_date.tzinfo is None:
        article_date = article_date.replace(tzinfo=tzutc())
    if start_date and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=tzutc())
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=tzutc())
    
    if start_date and end_date:
        return start_date <= article_date <= end_date
    elif start_date:
        return start_date <= article_date
    elif end_date:
        return article_date <= end_date
    else:
        return True

# Function to extract time periods from strings
def extract_time_periods(names):
    time_periods = {}
    if isinstance(names, str):
        names = [names]    
    for name_info in names:
        name_parts = name_info.split(" (")
        name = name_parts[0].strip()
        start_date, end_date = None, None
        
        # Look for Start and End times within the parts
        for part in name_parts[1:]:
            if 'Start:' in part:
                start_str = part.replace("Start:", "").replace("T00:00:00Z)", "").strip()
                try:
                    start_date = parser.parse(start_str)
                except (ValueError, parser.ParserError):
                    start_date = None
            elif 'End:' in part:
                end_str = part.replace("End:", "").replace("T00:00:00Z)", "").strip()
                try:
                    end_date = parser.parse(end_str)
                except (ValueError, parser.ParserError):
                    end_date = None
        
        time_periods[name] = (start_date, end_date)
    return time_periods

# Function to process and filter the JSON data
def process_json_data(json_data):
    result = {}
    for company in json_data:
        if (len(json_data) >= 2 and 'United States' in company['country']) or len(json_data)<=1:
            ticker = company['ticker']
            print(ticker)
            # Extract time periods for CEOs and board members
            # Add company info to the result
            result[ticker] = {
                'id_label': extract_time_periods(company.get('id_label', [])),
                'ticker': extract_time_periods(company.get('ticker', [])),
                'aliases': extract_time_periods(company.get('aliases', [])),
                'products': extract_time_periods(company.get('products', [])),
                'subsidiaries': extract_time_periods(company.get('subsidiaries', [])),
                'owned_entities': extract_time_periods(company.get('owned_entities', [])),
                'ceos': extract_time_periods(company.get('ceos', [])),
                'board_members': extract_time_periods(company.get('board_members', [])),
            }
    print(result)
    return result

# Process all JSON files in the 'info' folder
def read_and_process_json_files(folder_path):
    all_processed_data = {}    
    print(folder_path)
    for filename in os.listdir(folder_path):
        if filename.endswith('.json'):
            file_path = os.path.join(folder_path, filename)
            try:
                # 明确指定UTF-8编码
                with open(file_path, 'r', encoding='utf-8') as file:
                    json_data = json.load(file)
                    processed_data = process_json_data(json_data)
                    all_processed_data.update(processed_data)
            except UnicodeDecodeError:
                # 如果UTF-8失败，尝试其他常见编码
                print(f"UTF-8解码失败，尝试其他编码读取文件: {filename}")
                try:
                    with open(file_path, 'r', encoding='gbk') as file:
                        json_data = json.load(file)
                        processed_data = process_json_data(json_data)
                        all_processed_data.update(processed_data)
                except UnicodeDecodeError:
                    try:
                        with open(file_path, 'r', encoding='latin1') as file:
                            json_data = json.load(file)
                            processed_data = process_json_data(json_data)
                            all_processed_data.update(processed_data)
                    except Exception as e:
                        print(f"无法读取文件 {filename}: {e}")
            except Exception as e:
                print(f"处理文件 {filename} 时出错: {e}")
    return all_processed_data

# # Read and process JSON files
# folder_path = 'crypto'
# processed_data = read_and_process_json_files(folder_path)

# Append matched articles to the CSV file with all matched strings

def append_to_csv(source_name, ticker, matched_names, article):
    output_file = f'{source_name}_ticker_matched_articles/{ticker}_match.csv'
    write_header = not os.path.exists(output_file)
    article_datetime = parser.parse(article['date_time'])
    unix_timestamp = int(article_datetime.timestamp())
    
    data_to_append = {
        'time_unix': unix_timestamp,
        'date_time': article['date_time'],
        'text_matches': json.dumps(matched_names['text']),
        'title_matches': json.dumps(matched_names['title']),
        'title': article['title'],
        'url': article['url'],
        'source': article['source'],
        'source_url': article['source_url'],
        'article_text': article['article_text'],
    }
    df_to_append = pd.DataFrame([data_to_append])
    df_to_append.to_csv(output_file, mode='a', index=False, header=write_header)

def process_chunk(source_name, chunk, processed_data):
    for index, row in tqdm(chunk.iterrows(), total=chunk.shape[0], desc="Processing"):
        article_text = str(row['article_text']) if row['article_text'] else ""
        title = str(row['title']) if row['title'] else ""
        article_date = parser.parse(str(row['date_time'])) if pd.notna(row['date_time']) else None
        ticker_matches = {}  # Dictionary to hold all matches for this article

        def find_positions(pattern, text):
            return [match.start() for match in re.finditer(pattern, text)]

        # Check each ticker's data for matches
        for ticker, value in processed_data.items():
            text_matches = {}
            title_matches = {}
            for attribute, names in value.items():
                for name, (start_date, end_date) in names.items():
                    if is_within_period(article_date, start_date, end_date):
                        if name.isupper():
                            if len(name) > 1:
                                pattern = r'\b' + re.escape(name) + r'\b'
                                text_positions = find_positions(pattern, article_text)
                                title_positions = find_positions(pattern, title)
                                if text_positions:
                                    text_matches[name] = text_positions
                                if title_positions:
                                    title_matches[name] = title_positions
                        elif not (name.islower() and name.replace(' ', '').isalpha()):
                            text_match = fuzz.partial_ratio(article_text, name) > 95
                            title_match = fuzz.partial_ratio(title, name) > 95
                            if text_match:
                                text_matches[name] = find_positions(name, article_text)
                            if title_match:
                                title_matches[name] = find_positions(name, title)

            # If there were any matches for this ticker, add them to the article_matches
            if text_matches or title_matches:                
                ticker_matches[ticker] = {
                    'text': text_matches,
                    'title': title_matches
                }

        # Now write each set of matches to its respective CSV
        for ticker, matched_names in ticker_matches.items():
            # print(matched_names)
            append_to_csv(source_name, ticker, matched_names, row)


def sort_matched_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        
        # Custom parsing function for the datetime
        def parse_datetime(date_string):
            return parser.parse(date_string)

        # Apply the custom parsing function and create Unix timestamp if not present
        if 'time_unix' not in df.columns:
            df['date_time'] = df['date_time'].apply(parse_datetime)
            df['time_unix'] = df['date_time'].apply(lambda x: int(x.timestamp()))

        # Sort by Unix timestamp
        df_sorted = df.sort_values('time_unix', ascending=True)
        
        # Ensure 'time_unix' is an integer
        df_sorted['time_unix'] = df_sorted['time_unix'].astype(int)
        
        df_sorted.to_csv(file_path, index=False)
        print(f"Sorted and saved: {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")


if __name__ == '__main__':
    # 读取并处理 JSON 文件
    source_name = 'yahoo'
    folder_path = 'info/Icahn_filter'
    processed_data = read_and_process_json_files(folder_path)

    # 分块读取 CSV（防止内存爆）
    chunksize = 20000  # 每次处理 5 万行
    os.makedirs(f'{source_name}_ticker_matched_articles', exist_ok=True)

    for chunk in pd.read_csv('datasets/yahoo_articles_all_20250605.csv', chunksize=chunksize):
        num_processes = mp.cpu_count()
        sub_chunks = np.array_split(chunk, num_processes)

        with mp.Pool(processes=num_processes) as pool:
            list(tqdm(
                pool.starmap(process_chunk, [(source_name, sub_chunk, processed_data) for sub_chunk in sub_chunks]),
                total=len(sub_chunks)
            ))

    print("All matched CSV files have been processed.")

    # 按时间排序每个结果文件
    for file in os.listdir(f"{source_name}_ticker_matched_articles"):
        sort_matched_csv(f"{source_name}_ticker_matched_articles/{file}")

    print("All matched CSV files have been sorted by date and time.")



# # Append matched articles to the CSV file
# def append_to_csv(ticker, matched_name, article):
#     output_file = f'matched_articles/{ticker}_match.csv'
#     # Check if file exists and whether headers need to be written
#     write_header = not os.path.exists(output_file)
#     # Data to append
#     data_to_append = {
#         'matched_name': [matched_name],
#         'url': [article['url']],
#         'date_time': [article['date_time']],
#         'article_text': [article['article_text']]
#     }
#     # Convert data to DataFrame
#     df_to_append = pd.DataFrame(data_to_append)
#     # Append to CSV file
#     df_to_append.to_csv(output_file, mode='a', index=False, header=write_header)

# # Iterate over the news DataFrame and match with tickers
# for index, row in news_df.iterrows():
#     print(index)
#     article_text = row['article_text']
#     article_date = parser.parse(row['date_time'])
#     for ticker, value in processed_data.items():
#         for attribute, names in value.items():
#             if attribute in ['ceos', 'board_members']:  # These have time periods
#                 for name, (start_date, end_date) in names.items():
#                     if is_within_period(article_date, start_date, end_date):
#                         if fuzz.partial_ratio(article_text, name) > 95: 
#                             append_to_csv(ticker, name, row)
#             else:  # 'aliases', 'products', 'subsidiaries', 'owned_entities'
#                 for name in names:
#                     if fuzz.partial_ratio(article_text, name) > 95:  # Assuming a threshold score of 70
#                         append_to_csv(ticker, name, row)
    


# ... [Keep the previously defined functions] ...


# # Function to process a chunk of the DataFrame
# def process_chunk(chunk, processed_data):
#     for index, row in tqdm(chunk.iterrows(), total=chunk.shape[0], desc="Processing"):
#         article_text = row['article_text']
#         article_date = parser.parse(row['date_time'])
#         for ticker, value in processed_data.items():
#             for attribute, names in value.items():
#                 if attribute in ['ceos', 'board_members']:  # These have time periods
#                     for name, (start_date, end_date) in names.items():
#                         if is_within_period(article_date, start_date, end_date):
#                             if fuzz.partial_ratio(article_text, name) > 95: 
#                                 append_to_csv(ticker, name, row)
#                 else:  # 'aliases', 'products', 'subsidiaries', 'owned_entities'
#                     for name in names:
#                         if fuzz.partial_ratio(article_text, name) > 95:  # Assuming a threshold score of 70
#                             append_to_csv(ticker, name, row)

