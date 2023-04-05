# Full-Run

- Go `Google API Console` to apply a credential for upload purpose

- CAUTION:
1. Make sure adb will enable automatically
2. Make sure fasboot works, use test.py to check
3. Test suite must be kept in Downloads otherwise modify base_path

- ENV SETUP:
  - sudo apt-get install python3-pip
  - pip install termcolor
  - pip install gspread
  - pip install oauth2client
  
- Two ways to execute full_run.py
1. `python3 full_run.py "platform" "build" "test suite" full retry" "triage retry" "devices"`

   `python3 full_run.py sh tm ats 2 3 33f983b8 96104d9d b341002c`
2. run python3 full_run.py and input relative arguments
![S__71565314](https://user-images.githubusercontent.com/99638331/230031072-ff95caf4-3235-4ce6-a5a6-236fb06c6a45.jpg)
