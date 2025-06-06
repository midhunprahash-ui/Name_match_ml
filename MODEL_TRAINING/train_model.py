import pandas as pd
from thefuzz import fuzz
import jellyfish
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
import joblib
import numpy as np

# Loading the Dataset
df=pd.read_csv('/Users/midhun/Developer/Git/Name_match_ml/TRAINING_DATA/training_data_(4k).csv')

# Feature Engineering

def compute_features(row):
    uname = row['username']
    ename = row['employee_name']
    return pd.Series({
        'levenshtein': fuzz.ratio(uname, ename),
        'partial_ratio': fuzz.partial_ratio(uname, ename),
        'token_set_ratio': fuzz.token_set_ratio(uname, ename),
        'soundex_match': int(jellyfish.soundex(uname) == jellyfish.soundex(ename)),
        'metaphone_match': int(jellyfish.metaphone(uname) == jellyfish.metaphone(ename))
    })

features = df.apply(compute_features, axis=1)
df = pd.concat([df, features], axis=1)

# Preparing features & Labels

X = df[['levenshtein', 'partial_ratio', 'token_set_ratio', 'soundex_match', 'metaphone_match']]
y = df['label']

# Splitting Train & Test data

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=32)

# Training the RF model

rf = RandomForestClassifier(n_estimators=100, random_state=32)
rf.fit(X_train, y_train)

# Evaluating the model 

y_pred = rf.predict(X_test)
print(classification_report(y_test, y_pred))

joblib.dump(rf,'new_model.pkl')