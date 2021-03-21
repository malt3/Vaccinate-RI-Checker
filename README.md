# Vaccinate-RI-Checker
```
                        _             __          ____  ____
 _   ______ ___________(_)___  ____ _/ /____     / __ \/  _/
| | / / __ `/ ___/ ___/ / __ \/ __ `/ __/ _ \   / /_/ // /  
| |/ / /_/ / /__/ /__/ / / / / /_/ / /_/  __/  / _, _// /   
|___/\__,_/\___/\___/_/_/ /_/\__,_/\__/\___/  /_/ |_/___/   
                                                            
                __              __            
          _____/ /_  ___  _____/ /_____  _____
         / ___/ __ \/ _ \/ ___/ //_/ _ \/ ___/
        / /__/ / / /  __/ /__/ ,< /  __/ /    
        \___/_/ /_/\___/\___/_/|_|\___/_/     
                                      
                                       |
                 ,------------=--------|___________|
-=============%%%|         |  |______|_|___________|
                 | | | | | | ||| | | | |___________|
                 `------------=--------|           |
                                       |
                                                                

```

*Tool to notify users whenever new vaccination appointments are available in Rhode Island.*

## Installation
1. Clone this repo: `git clone https://github.com/malt3/Vaccinate-RI-Checker && cd Vaccinate-RI-checker`
2. Install dependencies: `pip3 install --user beautifulsoup4 requests`
    1. beautifulsoup4
    2. requests
3. Create a pushover account, install the app on your phone
4. Create an API token on pushover and write down the API Key
5. Enjoy ❤️

## Usage
```bash
python3 main.py PUSHOVER_USER_KEY PUSHOVER_API_KEY
```
