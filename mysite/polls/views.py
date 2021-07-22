from django.shortcuts import render, render_to_response
from django.http import HttpResponse
from sqlalchemy import create_engine
from django.views.decorators.cache import cache_page
from django.contrib.auth.decorators import login_required
from .charts import *
import pandas as pd
import numpy as np
import json
import six
import xlsxwriter


try:
    from io import BytesIO as IO
except ImportError:
    from io import StringIO as IO
import datetime

ENGINE = create_engine('mysql+pymysql://root:wangheng66941248@17.87.1.78:3306/Polls_DB')
DB_TABLE = "DummyData"
D_MULTI_SELECT = {
    'TC I': 'TC_I',
    'TC II': 'TC_II',
    'TC III': 'TC_III',
    'TC IV': 'TC_IV',
    '通用名|MOLECULE': 'MOLECULE',
    '商品名|PRODUCT': 'PRODUCT',
    '包装|PACKAGE': 'PACKAGE',
    '生产企业|CORPORATION': 'CORPORATION',
    '企业类型': 'MANUF_TYPE',
    '剂型': 'FORMULATION',
    '剂量': 'STRENGTH'

}


def sqlparse(context):
    #print(context)
    sql = "Select * from %s Where PERIOD = '%s' And UNIT = '%s'" % \
          (DB_TABLE, context['PERIOD_select'][0], context['UNIT_select'][0])

    # 下面循环处理多选部分
    for k, v in context.items():
        if k not in ['csrfmiddlewaretoken', 'DIMENSION_select', 'PERIOD_select', 'UNIT_select']:
            if k[-2:] == '[]':
                field_name = k[:-9]  # 如果键以[]结尾，删除_select[]取原字段名
            else:
                field_name = k[:-7]  # 如果键不以[]结尾，删除_select取原字段名
            selected = v  # 选择项
            sql = sql_extent(sql, field_name, selected)  # 未来可以通过进一步拼接字符串动态扩展sql语句
    return sql


def sql_extent(sql, field_name, selected, operator=" AND "):
    if selected is not None:
        statement = ''
        for data in selected:
            statement = statement + "'" + data + "', "
        statement = statement[:-2]
        print('当筛选里面有内容时，则内容是' + str(statement))
    if statement != '':
        sql = sql + operator + field_name + " in (" + statement + ")"
        print('sql的值是' + str(sql))
    return sql


def get_kpi(df):
    kpi = {}

    # 按列求和为市场总值的Series
    market_total = df.sum(axis=1)
    # 最后一行（最后一个DATE）就是最新的市场规模
    market_size = market_total.iloc[-1]
    # 市场按列求和，倒数第5行（倒数第5个DATE）就是同比的市场规模，可以用来求同比增长率
    market_gr = (market_total.iloc[-1] / market_total.iloc[-5] - 1)
    # 因为数据第一年是四年前的同期季度，时间序列收尾相除后开四次方根可得到年复合增长率
    market_cagr = (market_total.iloc[-1] / market_total.iloc[0]) ** (0.25) - 1
    if market_size == np.inf or market_size == -np.inf:
        market_size = "N/A"
    if market_gr == np.inf or market_gr == -np.inf:
        market_gr = "N/A"
    if market_cagr == np.inf or market_cagr == -np.inf:
        market_cagr = "N/A"

    return {
        "market_size": market_size,
        "market_gr": "{0: .1%}".format(market_gr),
        "market_cagr": "{0: .1%}".format(market_cagr),
    }


def ptable(df):
    # 份额
    df_share = df.transform(lambda x: x / x.sum(), axis=1)

    # 同比增长率，要考虑分子为0的问题
    df_gr = df.pct_change(periods=4)
    df_gr.dropna(how='all', inplace=True)
    df_gr.replace([np.inf, -np.inf], np.nan, inplace=True)

    # 最新滚动年绝对值表现及同比净增长
    df_latest = df.iloc[-1, :]
    df_latest_diff = df.iloc[-1, :] - df.iloc[-5, :]

    # 最新滚动年份额表现及同比份额净增长
    df_share_latest = df_share.iloc[-1, :]
    df_share_latest_diff = df_share.iloc[-1, :] - df_share.iloc[-5, :]

    # 进阶指标EI，衡量与市场增速的对比，高于100则为跑赢大盘
    df_gr_latest = df_gr.iloc[-1, :]
    df_total_gr_latest = df.sum(axis=1).iloc[-1] / df.sum(axis=1).iloc[-5] - 1
    df_ei_latest = (df_gr_latest + 1) / (df_total_gr_latest + 1) * 100

    df_combined = pd.concat(
        [df_latest, df_latest_diff, df_share_latest, df_share_latest_diff, df_gr_latest, df_ei_latest], axis=1)
    df_combined.columns = ['最新滚动年销售额',
                           '净增长',
                           '份额',
                           '份额同比变化',
                           '同比增长率',
                           'EI']

    return df_combined


@login_required
def search(request, column, kw):
    sql = "SELECT DISTINCT %s FROM %s WHERE %s like '%%%s%%' limit 10" % (column, DB_TABLE, column, kw)
    try:
        df = pd.read_sql_query(sql, ENGINE)
        l = df.values.flatten().tolist()
        results_list = []
        for element in l:
            option_dict = {'name': element,
                           'value': element,
                           }
            results_list.append(option_dict)
        res = {
            "success": True,
            "results": results_list,
            "code": 200,
        }
    except Exception as e:
        res = {
            "success": False,
            "errMsg": e,
            "code": 0,
        }
    return HttpResponse(json.dumps(res, ensure_ascii=False), content_type="application/json charset=utf-8")  # 返回结果必须是json格式


def get_distinct_list(column, db_table):
    sql = "Select DISTINCT " + column + " From " + db_table
    df = pd.read_sql_query(sql, ENGINE)
    li = df.values.flatten().tolist()
    return li


@login_required
def query(request):
    form_dict = dict(six.iterlists(request.GET))
    print('form_dict的值是' + str(form_dict))
    pivoted = get_df(form_dict)

    # KPI
    kpi = get_kpi(pivoted)
    table = ptable(pivoted)
    table = pd.DataFrame(table.to_records())
    table = table.to_html(formatters=build_formatters_by_col(table),
                          classes='ui selectable celled table',
                          justify='center',
                          table_id='ptable',
                          index=False
                          )
    # Pyecharts
    bar_total_trend = json.loads(prepare_chart(pivoted, 'bar_total_trend', form_dict))

    context = {
        "market_size": kpi["market_size"],
        "market_gr": kpi["market_gr"],
        "market_cagr": kpi["market_cagr"],
        'ptable': table,
        'bar_total_trend': bar_total_trend,
    }

    return HttpResponse(json.dumps(context, ensure_ascii=False), content_type="application/json charset=utf-8")


def build_formatters_by_col(df):
    format_abs = lambda x: '{:,.0f}'.format(float(x))
    format_share = lambda x: '{:.1%}'.format(float(x))
    format_gr = lambda x: '{:.1%}'.format(float(x))
    format_currency = lambda x: '¥{:,.0f}'.format(float(x))
    d = {}
    for column in df.columns[1:]:
        if '份额' in column or '贡献' in column:
            d[column] = format_share
        elif '价格' in column or '单价' in column:
            d[column] = format_currency
        elif '同比增长'in column or '增长率' in column or 'CAGR' in column or '同比变化' in column:
            d[column] = format_gr
        else:
            d[column] = format_abs
    return d


@login_required
def index(request):
    mselect_dict = {}
    for key, value in D_MULTI_SELECT.items():
        mselect_dict[key] = {}
        mselect_dict[key]['select'] = value

    context = {
        'mselect_dict': mselect_dict
    }

    return render(request, 'Polls/display.html', context)


D_TRANS = {
            'MAT': '滚动年',
            'QTR': '季度',
            'Value': '金额',
            'Volume': '盒数',
            'Volume (Counting Unit)': '最小制剂单位数',
            '滚动年': 'MAT',
            '季度': 'QTR',
            '金额': 'Value',
            '盒数': 'Volume',
            '最小制剂单位数': 'Volume (Counting Unit)'
           }


def prepare_chart(df,  # 输入经过pivoted方法透视过的df，不是原始df
                  chart_type,  # 图表类型字符串，人为设置，根据图表类型不同做不同的Pandas数据处理，及生成不同的Pyechart对象
                  form_dict,  # 前端表单字典，用来获得一些变量作为图表的标签如单位
                  ):
    label = D_TRANS[form_dict['PERIOD_select'][0]] + D_TRANS[form_dict['UNIT_select'][0]]
    print(label)

    if chart_type == 'bar_total_trend':
        df_abs = df.sum(axis=1)  # Pandas列汇总，返回一个N行1列的series，每行是一个date的市场综合
        df_abs.index = df_abs.index.strftime("%Y-%m")  # 行索引日期数据变成2020-06的形式
        df_abs = df_abs.to_frame()  # series转换成df
        df_abs.columns = [label]  # 用一些设置变量为系列命名，准备作为图表标签
        df_gr = df_abs.pct_change(periods=4)  # 获取同比增长率
        df_gr.dropna(how='all', inplace=True)  # 删除没有同比增长率的行，也就是时间序列数据的最前面几行，他们没有同比
        df_gr.replace([np.inf, -np.inf, np.nan], '-', inplace=True)  # 所有分母为0或其他情况导致的inf和nan都转换为'-'

        chart = echarts_stackbar(df=df_abs,
                                 df_gr=df_gr
                                 )  # 调用stackbar方法生成Pyecharts图表对象
        print(chart)
        return chart.dump_options()  # 用json格式返回Pyecharts图表对象的全局设置
    else:
        return None


def get_df(form_dict, is_pivoted=True):
    sql = sqlparse(form_dict)  # sql拼接
    df = pd.read_sql_query(sql, ENGINE)  # 将sql语句结果读取至Pandas Dataframe

    if is_pivoted is True:
        dimension_selected = form_dict['DIMENSION_select'][0]
        if dimension_selected[0] == '[':

            column = dimension_selected[1:][:-1]
        else:
            column = dimension_selected
            print('dimension_select的值是' + str(column))

        pivoted = pd.pivot_table(df,
                                 values='AMOUNT',  # 数据透视汇总值为AMOUNT字段，一般保持不变
                                 index='DATE',  # 数据透视行为DATE字段，一般保持不变
                                 columns=column,  # 数据透视列为前端选择的分析维度
                                 aggfunc=np.sum)  # 数据透视汇总方式为求和，一般保持不变
        if pivoted.empty is False:
            pivoted.sort_values(by=pivoted.index[-1], axis=1, ascending=False, inplace=True)  # 结果按照最后一个DATE表现排序

        return pivoted
    else:
        return df


@login_required
def export(request, type):
    form_dict = dict(six.iterlists(request.GET))
    if type =='pivoted':
        df = get_df(form_dict)
    elif type =='raw':
        df = get_df(form_dict, is_pivoted=False)
    excel_file = IO()
    xlwriter = pd.ExcelWriter(excel_file, engine='xlsxwriter')
    df.to_excel(xlwriter, 'data', index=True)
    xlwriter.save()
    xlwriter.close()
    excel_file.seek(0)

    response = HttpResponse(excel_file.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    now = datetime.datetime.now().strftime("%Y%M%d%H%M%S")
    response['Content-Disposition'] = 'attachment; filename=' + now + '.xlsx'
    return response





