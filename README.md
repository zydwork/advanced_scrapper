# Advanced High Speed Universal Scrapper

The currently available program is `constant_rate_scrapper.py`

- Muti-thread Firefox-geckodriver, queueing mechanism
- Send requests at a constant rate, great for avoiding rate limit
- Rate limit detection and pausing mechainsm
- Use template form `extractors` folder (Yahoo Finance as example)
- Log both succeed and failed articles, automatically resume the progress when restart, simple CSV storage

`yahoo_links_selenium.py` is used to get all the recorded Yahoo Finance news links on Internet Archive through its CDX server. It loops through prefix "00*" - "zz*", since on some link prefixes only return limited amount of results because there's too much urls. All the succeed fetches will be cached in the "parts" folder (also capable for automatic resuming after restart). Finally it drops the duplicates and output a CSV file that could feed to the scrapper. 

`experimental` folder holds all the experimental programs, future developmet including distributed system and more advanced with computer vision universal templateless scrapper. 

`ticker_symbol_query` is used to get the information for each ticker (company name, products, key people etc), which can be further matched with news. Note: consider using VPN to use an American IP if error. 

`match_keywords.py` match the information from Wikidata to get the according news for each ticker. To use this dataset, you can download the premade dataset there from my [HuggingFace](https://huggingface.co/datasets/edaschau/financial_news)



![image-20250824023529789](./README.png)

