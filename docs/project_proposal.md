# Investment and Trading Capstone Project: ETFs Price Indicator

In this project, we adapt [this proposal](https://docs.google.com/document/d/1ycGeb1QYKATG6jvz74SAMqxrlek9Ed4RYrzWNhWS-0Q/pub) by focusing on building an interactive dashboard to predict closing prices for a set of indices. Our goal is to focus on indices that have been performing  around the SP500 or above, since this index is a good measure of the market as a whole. We aim at producing a dashboard that displays forecasts at several time steps into the future, together with estimates of uncertainty bands, and that retrains the forecasting model daily, in order for the forecast to use the most up to date data. We will have to have a daily job (e.g., using an AWS step function) that extracts and preprocesses the latest price data, launches an instance to update the model, saves the updated model to S3 launches another instance for inference and to save the results to S3. Then, we can have the dashboard running on a small EC2 instance just for inference and serving of the dashboard. The results for all indices can then be refreshed daily on the instance responsible for the serving.

Overall we propose the following steps for the project:

1. Perform data exploration to select a subset of indices to include in our supported indices to forecast.
2. Model development: Here the goal is to preform an offline study to select the best model training approach. It will include:
   - Data cleaning/Preprocessing
   - Feature engineering
   - Hyperparameter optimization
   - Final model training & Evaluation (with temporal cross validation)
3. Develop Step Function workflow for daily model retraining
4. Dashboard development
5. Deployment & Report Submission

The goal is for the examiners of this capstone project to be able to interact with the final dashboard.
