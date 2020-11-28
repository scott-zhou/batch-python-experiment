# Importing the libraries
import argparse
import pandas as pd
import numpy as np
from sklearn import metrics
from sklearn.model_selection import train_test_split
import random_forest
import linear_regression
import mlp
import svm

# Importing the Boston Housing dataset
from sklearn.datasets import load_boston


def parse_args():
    parser = argparse.ArgumentParser(description='Boston house price.')
    parser.add_argument('config', type=str,
                        help='Config file for select a method.')
    parser.add_argument('output', type=str,
                        help='Output filename')
    return parser.parse_args()


def default_method(X_train, X_test, y_train, y_test):
    return 0


def get_X_y():
    boston = load_boston()

    # Initializing the dataframe
    data = pd.DataFrame(boston.data)

    # Adding the feature names to the dataframe
    data.columns = boston.feature_names

    # Adding target variable to dataframe
    data['PRICE'] = boston.target
    # Median value of owner-occupied homes in $1000s

    # Spliting target variable and independent variables
    X = data.drop(['PRICE'], axis=1)
    y = data['PRICE']

    # Splitting to training and testing data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=4)
    return X_train, X_test, y_train, y_test


if __name__ == '__main__':
    args = parse_args()
    with open(args.config) as f:
        first_line = f.readline().strip().lower()
    methods = {
        "random forest": random_forest.train_evaluation_model,
        "linear regression": linear_regression.train_evaluation_model,
        "multi-layer perceptron": mlp.train_evaluation_model,
        "svm": svm.train_evaluation_model
    }
    X_train, X_test, y_train, y_test = get_X_y()
    acc = methods.get(first_line, default_method)(
        X_train, X_test, y_train, y_test)
    print(f"The accuracy is {acc}")
    with open(args.output, "w") as fd:
        fd.write(f'{first_line}\n')
        fd.write(f'R-squared Score: {acc}')
