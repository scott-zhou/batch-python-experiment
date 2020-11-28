import numpy as np
from sklearn import metrics
# Import MLP Regressor
from sklearn.neural_network import MLPRegressor


def train_evaluation_model(X_train, X_test, y_train, y_test):
    # Train the model using the training sets
    reg = MLPRegressor(random_state=1, max_iter=500).fit(X_train, y_train)

    # Model prediction on train data
    y_pred = reg.predict(X_train)

    # Model Evaluation
    print("Model Evaluation on training data")
    print('R^2:', metrics.r2_score(y_train, y_pred))
    print('Adjusted R^2:', 1 - (1-metrics.r2_score(y_train, y_pred))
          * (len(y_train)-1)/(len(y_train)-X_train.shape[1]-1))
    print('MAE:', metrics.mean_absolute_error(y_train, y_pred))
    print('MSE:', metrics.mean_squared_error(y_train, y_pred))
    print('RMSE:', np.sqrt(metrics.mean_squared_error(y_train, y_pred)))
    print("")

    # Predicting Test data with the model
    y_test_pred = reg.predict(X_test)

    # Model Evaluation
    acc_mlp = metrics.r2_score(y_test, y_test_pred)
    print("Model Evaluation on test data")
    print('R^2:', acc_mlp)
    print('Adjusted R^2:', 1 - (1-metrics.r2_score(y_test, y_test_pred))
          * (len(y_test)-1)/(len(y_test)-X_test.shape[1]-1))
    print('MAE:', metrics.mean_absolute_error(y_test, y_test_pred))
    print('MSE:', metrics.mean_squared_error(y_test, y_test_pred))
    print('RMSE:', np.sqrt(metrics.mean_squared_error(y_test, y_test_pred)))
    return acc_mlp * 100
