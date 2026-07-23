# Tennis Data Analysis

# Overview

This project analyzes a tennis dataset to answer a collection of analytical questions related to players, tournaments, rankings, match statistics, and fan voting behavior.
The analyses were implemented using Python,Pandas and notebook.

---

# Project Structure

```
Tennis-project/
│
├── codes/
│   ├── ReadFileMethodOne/
│   │     ├── analysis.ipynb
│   ├── ReadFileMethodTwo/
│   │     ├── build_tennis_db.py
│   │     ├── test.py
│   │     ├── unzip_helper.py
│
├── questions/
│   ├── answers/
│   │     ├── 001/
│   │     │      ├── Q1.ipynb
│   │     ├── 002/
│   │     │      ├── Q2.ipynb
│   │     └── ...
│   ├── status.text
│
├── new-questions/
│   ├── answers/
│   │     ├── 001/
│   │     │      ├── Q1.ipynb
│   │     ├── 002/
│   │     │      ├── Q2.ipynb
│   │     └── ...
│   ├── new-questions-status.text
│
├── README.md
├── requirements.txt
└── .gitignore
```

---

## Dataset

The dataset consists of a collection of compressed ZIP archives containing tennis-related data. Each archive includes one or more **Parquet** files representing different aspects of professional tennis matches, such as player information, match events, tournament details, rankings, game statistics, fan votes, and betting odds.

The data is organized into multiple relational tables, where each table stores information about a specific entity. These tables are linked through common identifiers (e.g., `match_id`) and are combined as needed to answer the analytical questions in this project.

---

# Requirements

Install the required packages:

```bash
pip install -r requirements.txt
```

Main libraries:

- pandas
- numpy
- pyarrow

---

# Analytical Questions

The project answers the following questions:

| #  | Question |
|----|----------|
| 1  | How many tennis players are included in the dataset? |
| 2  | What is the average height of the players? |
| 3  | Which player has the highest number of wins? |
| 4  | What is the longest match recorded? |
| 5  | How many sets are typically played in a tennis match? |
| 6  | Which country has produced the most successful tennis players? |
| 7  | What is the average number of aces per match? |
| 8  | Is there a difference in double faults based on gender? |
| 9  | Which player has won the most tournaments in a single month? |
| 10 | Is there a correlation between player height and ranking? |
| 11 | What is the average duration of matches? |
| 12 | Average games per set (men vs women) |
| 13 | Distribution of left-handed vs right-handed players |
| 14 | Most common tournament surface |
| 15 | Number of represented countries |
| 16 | Highest winning percentage against Top-10 opponents |
| 17 | Average breaks of serve per match |
| 18 | Which match was the most predictable based on votes? |
| 19 | What is the average BMI of the players? |
| 20 | What percentage of matches do players win when they are in their own country? |
| 21 | In market_name=full_time, is there a significant difference between the initial odds of winners and losers? |
| 22 | Which tournament is the most competitive one ,based on the percentage of matches which finish in the final set? |
| 23 | Which tournament had the highest upset(wonder) rate? |
| 24 | Does winning the first set increase the chances of winning the entire match? |
| 25 | Do right-handed players perform better on grass courts compared to left-handed players? |
| 26 | How does the average weight of winning players compare to that of losing players across different gender? |
---
## 📄 Project Report
For a detailed analysis, explanations of the methodologies, and the final results of the questions, please refer to the comprehensive report:
* **[report-tennis-project.pdf](./report-tennis-project.pdf)**
---

# Data Cleaning

The analyses include several preprocessing steps:

- Removing duplicated records
- Handling missing values
- Merging multiple tables
- Aggregating repeated snapshots
- Feature engineering

---

# Running the Project

1. Clone the repository

```bash
git clone <repository-url>
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. There are different methods to set up the data and run the notebooks, depending on the questions you are exploring.

### 🔹 Method 1: For Questions Q[4, 6, 7, 13, 16, 19, 22, 23]
1. Collect all 60 zip files of the dataset and place them in a single folder.
2. Open the notebook `code/ReadFileMethodOne/analysis.ipynb`.
3. Copy and paste the path of your zip folder into the first cell of the notebook.
4. Run the cells sequentially to extract the files and build the required tables in that directory.
5. For each specific question, open the corresponding notebook inside `questions/answers/`, paste the path in the first cell, and run the cells.

### 🔹 Method 2: For Questions Q[1, 2, 3, 11, 12, 17, 19, 20, 21]
1. Navigate to the `code/ReadFileMethodTwo` directory.
2. Run `unzip_helper.py` (providing the correct path to your zip files) to extract all dataset files.
3. Copy `build_tennis_db.py` to the folder where the unzipped files are located, and run it. This script will consolidate the Parquet files and build the DuckDB database (adding the `snapshot_date` partition column).
4. Once the database is built, you can run the notebooks for the questions listed above. **Note:** Make sure to update the database path in the first cell of each notebook before execution.

### 🔹 Method 3: For Questions Q[5, 8, 9, 10, 14, 15, 24, 25, 26]
1. Locate the folder where you have already unzipped the dataset files.
2. For the questions listed above, open the respective notebook inside the questions directory.
3. Simply update the path to point directly to your unzipped files directory in the first cell of the notebook, and you are ready to run the cells.

---

# Contributors

- Sepideh
- Marzieh
- Sanaz