from typing import Callable, Dict, Iterable, Optional, Union

import numpy as np
import pandas as pd


def filter_covid_df(
    response_var: str,
    df: Optional[pd.DataFrame] = None,
    min_date: Optional[pd.Timestamp] = None,
    max_date: Optional[pd.Timestamp] = None,
    gender: Optional[Iterable[str]] = None,
    region: Optional[Iterable[str]] = None,
) -> pd.DataFrame:

    """
    Filter the COVID-19 DataFrame generated by Instituto de Salud Carlos III
    (https://cnecovid.isciii.es/covid19/).

    Parameters
    ----------
    response_var : str
        The response variable to be chosen. It must be one of the following:
            - "num_casos": Number of infected people.
            - "num_hosp": Number of hospitalized patients.
            - "num_uci": Number of ICU hospitalized patients.
            - "num_def": Number of fatalities.
    df : Optional[pd.DataFrame], optional
        The COVID-19 DataFrame. If None, it is downloaded from the website. By
        default, None.
    min_date : Optional[pd.Timedelta], optional
        The minimum date to be considered. If None, it coincides with the first
        non-zero response variable date. By default, None.
    max_date : Optional[pd.Timedelta], optional
        The maximum date to be considered. If None, it coincides with the
        maximum date of the DataFrame. By default, None.
    gender : Optional[Iterable[str]], optional
        The gender (male and/or female) to be considered. If None, both genders
        and undetermined gender ("NC") are taken. By default, None.
    region : Optional[Iterable[str]], optional
        The province ISO code to be considered. The allowed codes are available
        on the province_es.csv on the column "code". If None, all regions  are
        taken. By default, None.

    Returns
    -------
    pd.DataFrame
        The filtered DataFrame.

    Raises
    ------
    ValueError
        If `response_var` is not an allowed response variable.
    ValueError
        If `gender` are not allowed gender categories.
    ValueError
        If `region` are not allowed ISO codes.
    """

    # If not Dataframe provided, download it
    if df is None:
        df = pd.read_csv(
            r"https://cnecovid.isciii.es/covid19/resources/casos_hosp_uci_def_sexo_edad_provres.csv"
        )
    # Select the columns of interest
    if response_var not in ["num_casos", "num_hosp", "num_uci", "num_def"]:
        raise ValueError("Provide a suitable response variable name.")
    df = df.filter(items=["provincia_iso", "sexo", "grupo_edad", "fecha", response_var])
    # Select the correct gender and region
    if gender is not None:
        if len(set(gender) - set(["H", "M"])) > 0:
            raise ValueError("Provide suitable gender categories.")
        df = df.loc[df["sexo"].isin(gender)]
    if region is not None:
        iso_codes = pd.read_csv("../data/provinces_es.csv")["code"]
        if len(set(region) - set(iso_codes)) > 0:
            raise ValueError("Provide suitable region codes.")
        df = df.loc[df["provincia_iso"].isin(region)]
    # Aggregate the response variable
    df = df.groupby(["grupo_edad", "fecha"]).agg({response_var: np.sum}).reset_index()
    # Convert fecha to datetime
    df["fecha"] = pd.to_datetime(df["fecha"], infer_datetime_format=True)
    # Make the group ages a categorical variable
    df["grupo_edad"] = df["grupo_edad"].astype("category")
    # If no minimum date is provided, take first non-zero response variable date
    if min_date is None:
        min_date = (df.groupby(["fecha"])[response_var].sum().cumsum() != 0).idxmax()
    mask_min_date = df["fecha"] >= min_date
    # If no maximum date is provided, take second maximum date available
    # (maximum date is set to 0 in the downloaded file)
    if max_date is None:
        max_date = df["fecha"].max()
    mask_max_date = df["fecha"] < max_date

    df = df[mask_max_date & mask_min_date]
    # Sort the dataframe by date and age group
    df = df.sort_values(by=["fecha", "grupo_edad"], ascending=[True, True])
    return df


def agg_covid_by_age(
    df: pd.DataFrame,
    response_var: str,
    agg_method: Union[Callable, str] = np.sum,
) -> pd.DataFrame:

    """Aggregates the filtered COVID-19 DataFrame by age.

    Parameters
    ----------
    df : pd.DataFrame
        The filtered COVID-19 DataFrame.
    response_var : str
        The response variable chosen to filter the DataFrame.
    agg_method : Union[Callable, str], optional
        The aggregation method used. By default, np.sum.

    Returns
    -------
    pd.DataFrame
        The aggregated by age DataFrame.

    Raises
    ------
    ValueError
        If `response_var` is not an allowed response variable.
    """

    if response_var not in ["num_casos", "num_hosp", "num_uci", "num_def"]:
        raise ValueError("Provide a suitable response variable name.")
    df = df.groupby(["fecha"]).agg({response_var: agg_method})
    return df


def pivot_covid_df(df: pd.DataFrame, response_var: str) -> pd.DataFrame:

    """
    Pivot the filtered COVID-19 DataFrame. The index of the final Dataframe are
    the dates and the columns correspond to the age group.

    df : pd.DataFrame
        The filtered COVID-19 DataFrame.
    response_var : str
        The response variable chosen to filter the DataFrame.

    Returns
    -------
    pd.DataFrame
        The pivoted COVID-19 DataFrame.

    Raises
    ------
    ValueError
        If `response_var` is not an allowed response variable.
    """

    if response_var not in ["num_casos", "num_hosp", "num_uci", "num_def"]:
        raise ValueError("Provide a suitable response variable name.")

    df = df.query("grupo_edad != 'NC'").pivot(
        index="fecha", columns="grupo_edad", values=response_var
    )
    return df


def get_days_from_covid_df(df: pd.DataFrame) -> np.ndarray:

    """
    Get the days from first date present in the filtered COVID-19 DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        The pivoted or the aggregated by age COVID-19 DataFrame.

    Returns
    -------
    np.ndarray
        The ordered array containing the days from first record.
    """

    return (
        (df.index.to_series().diff() / np.timedelta64(1, "D")).fillna(0).cumsum().values
    )


def displaced_forecast_covid(
    deriv: np.ndarray,
    xmax: Union[int, float],
    lag: Union[int, float] = 0,
    factor_deriv: Union[int, float] = 1,
) -> Dict[str, Union[np.ndarray, Union[int, float]]]:

    """
    Compute the most extreme point in the forecast prediction and the
    coordinates of the points where constraints are imposed.

    Parameters
    ----------
    deriv : np.ndarray
        Value of the growth rates in the first wave.
    xmax : Union[int, float]
        Last point of the fitting region.
    lag : Union[int, float], optional
        The lag factor of the points in the second wave. By default, 0.
    factor_deriv : Union[int, float], optional
        The derivative factor needed to multiplied the growth rates in the first
        wave. By default, 1.

    Returns
    -------
    Dict[str, Union[np.ndarray, Union[int, float]]]
        A dictionary containing the following items:
        - `x_last`: The most extreme point in the forecast prediction.
        - `x_pred`: The points where the growth rates are enforced.
        - `deriv_pred`: The prediction derivative values.
    """

    # Get the most extreme point in the forecast prediction
    x_last = xmax + lag * len(deriv)
    # Get the derivatives multiplied by the `factor_deriv`
    deriv_pred = np.array([elem * factor_deriv for elem in deriv])
    # Get the values where the derivatives of the curve are imposed
    x_pred = np.arange(xmax + lag, x_last + lag, lag)
    return {"x_last": x_last, "x_pred": x_pred, "deriv_pred": deriv_pred}
