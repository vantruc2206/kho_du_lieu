// ===================================================================
// SSIS Script Component (Transformation) cho Data Flow "DFT_Fact_DailyPrice"
// Chế độ: Output 0 là ASYNCHRONOUS (SynchronousInputID = None)
// Dòng vào phải được SORT theo stock_key rồi trade_date (tăng dần)
// Tính: pct_change, sentiment, anomaly, risk_score, event_key, 4 chỉ số khủng hoảng
// ===================================================================
using System;
using System.Collections.Generic;
using Microsoft.SqlServer.Dts.Pipeline.Wrapper;
using Microsoft.SqlServer.Dts.Runtime.Wrapper;

[Microsoft.SqlServer.Dts.Pipeline.SSISScriptComponentEntryPointAttribute]
public class ScriptMain : UserComponent
{
    class R
    {
        public int StockKey, IndustryKey, DateKey, EventKey;
        public DateTime Date;
        public long Volume;
        public decimal Close;
        public decimal? Open, High, Low;
        public decimal Turnover, Vola;
        public bool HasVola;
        public bool HasPct;
        public decimal Pct, Sentiment, Risk;
        public int Anomaly;
        public bool HasCrisis;
        public decimal MaxDd, Trough, Loss;
        public int? Recovery;
    }

    // Giai đoạn khủng hoảng: THỨ TỰ phải khớp event_key 1..12 trong Dim_CrisisEvent (DW_KhoiTao.sql)
    static readonly Tuple<int, DateTime, DateTime>[] Phases = new Tuple<int, DateTime, DateTime>[]
    {
        T(1,  2007,3,13, 2009,2,24), T(2,  2009,2,25, 2009,10,31),
        T(3,  2010,11,1, 2011,12,31), T(4, 2012,1,1,  2012,12,31),
        T(5,  2018,4,10, 2018,12,31), T(6, 2019,1,1,  2019,12,31),
        T(7,  2020,1,20, 2020,3,31),  T(8, 2020,4,1,  2020,12,31),
        T(9,  2022,1,5,  2022,11,15), T(10,2022,11,16,2023,12,31),
        T(11, 2025,4,2,  2025,4,9),   T(12,2025,4,10, 2025,12,31)
    };

    static Tuple<int, DateTime, DateTime> T(int k, int y1, int m1, int d1, int y2, int m2, int d2)
    {
        return new Tuple<int, DateTime, DateTime>(k, new DateTime(y1, m1, d1), new DateTime(y2, m2, d2));
    }

    List<R> cur = new List<R>();
    int curStock = int.MinValue;

    public override void Input0_ProcessInput(Input0Buffer Buffer)
    {
        while (Buffer.NextRow())
        {
            Input0_ProcessInputRow(Buffer);
        }
        if (Buffer.EndOfRowset())
        {
            FlushStock();
            Output0Buffer.SetEndOfRowset();
        }
    }

    public override void Input0_ProcessInputRow(Input0Buffer Row)
    {
        if (Row.closeprice_IsNull || Row.volume_IsNull || Row.tradedate_IsNull) return;

        if (cur.Count > 0 && Row.stockkey != curStock) FlushStock();
        curStock = Row.stockkey;

        R r = new R();
        r.StockKey = Row.stockkey;
        r.IndustryKey = Row.industrykey;
        r.Date = Row.tradedate;
        r.DateKey = r.Date.Year * 10000 + r.Date.Month * 100 + r.Date.Day;
        r.Volume = Row.volume;
        r.Close = Row.closeprice;
        if (!Row.openprice_IsNull) r.Open = Row.openprice;
        if (!Row.highprice_IsNull) r.High = Row.highprice;
        if (!Row.lowprice_IsNull) r.Low = Row.lowprice;
        cur.Add(r);
    }

    static decimal Clip(decimal v, decimal max)
    {
        if (v > max) return max;
        if (v < -max) return -max;
        return Math.Round(v, 4);
    }

    static int FindEvent(DateTime d)
    {
        foreach (var p in Phases)
            if (d >= p.Item2 && d <= p.Item3) return p.Item1;
        return 0;
    }

    void FlushStock()
    {
        int n = cur.Count;
        if (n == 0) return;

        // 1) Chỉ số theo từng ngày
        for (int i = 0; i < n; i++)
        {
            R r = cur[i];
            r.EventKey = FindEvent(r.Date);

            // turnover (tỷ đồng): volume x close x 1000 / 1e9  (giá tính theo nghìn đồng)
            r.Turnover = r.Volume * r.Close * 1000m / 1000000000m;

            // volatility: (high - low) / close x 100
            if (r.High.HasValue && r.Low.HasValue && r.Close > 0)
            {
                r.Vola = (r.High.Value - r.Low.Value) / r.Close * 100m;
                r.HasVola = true;
            }

            // pct_change và sentiment
            if (i > 0 && cur[i - 1].Close > 0)
            {
                r.HasPct = true;
                r.Pct = (r.Close - cur[i - 1].Close) / cur[i - 1].Close * 100m;
                r.Sentiment = Math.Sign(r.Pct);
            }

            // anomaly: volume > TB20 + 2 x độ lệch chuẩn mẫu của tối đa 20 phiên trước (cần >= 2 phiên)
            int start = Math.Max(0, i - 20);
            int cnt = i - start;
            r.Anomaly = 0;
            if (cnt >= 2)
            {
                double sum = 0;
                for (int k = start; k < i; k++) sum += cur[k].Volume;
                double mean = sum / cnt;
                double ss = 0;
                for (int k = start; k < i; k++) ss += (cur[k].Volume - mean) * (cur[k].Volume - mean);
                double sd = Math.Sqrt(ss / (cnt - 1));
                if (r.Volume > mean + 2 * sd) r.Anomaly = 1;
            }

            // risk_score = 0.5 x volatility + 0.5 x |sụt so với đỉnh 60 phiên|
            decimal peak = 0;
            for (int k = Math.Max(0, i - 59); k <= i; k++)
                if (cur[k].Close > peak) peak = cur[k].Close;
            decimal dd60 = peak > 0 ? Math.Abs((r.Close - peak) / peak * 100m) : 0m;
            r.Risk = 0.5m * (r.HasVola ? r.Vola : 0m) + 0.5m * dd60;
        }

        // 2) Chỉ số theo từng giai đoạn khủng hoảng của mã này
        Dictionary<int, List<int>> byEvent = new Dictionary<int, List<int>>();
        for (int i = 0; i < n; i++)
        {
            int e = cur[i].EventKey;
            if (e == 0) continue;
            if (!byEvent.ContainsKey(e)) byEvent[e] = new List<int>();
            byEvent[e].Add(i);
        }

        foreach (var kv in byEvent)
        {
            List<int> idx = kv.Value;
            decimal firstClose = cur[idx[0]].Close;
            decimal minClose = decimal.MaxValue, peakClose = 0, runPeak = 0, maxDd = 0;
            int troughIdx = idx[0];
            double sumVol = 0;

            foreach (int i in idx)
            {
                decimal c = cur[i].Close;
                if (c < minClose) { minClose = c; troughIdx = i; }   // lấy ngày đáy sớm nhất khi bằng nhau
                if (c > peakClose) peakClose = c;
                if (c > runPeak) runPeak = c;
                if (runPeak > 0)
                {
                    decimal dd = (c - runPeak) / runPeak * 100m;
                    if (dd < maxDd) maxDd = dd;
                }
                sumVol += cur[i].Volume;
            }
            double avgVol = sumVol / idx.Count;

            decimal trough = firstClose > 0 ? minClose / firstClose * 100m : 0m;
            decimal loss = (firstClose - minClose) * (decimal)avgVol * 1000m / 1000000000m;

            int? recovery = null;
            for (int j = troughIdx + 1; j < n; j++)
            {
                if (cur[j].Close >= peakClose)
                {
                    recovery = (cur[j].Date - cur[troughIdx].Date).Days;
                    break;
                }
            }

            foreach (int i in idx)
            {
                R r = cur[i];
                r.HasCrisis = true;
                r.MaxDd = maxDd;
                r.Trough = trough;
                r.Loss = loss;
                r.Recovery = recovery;
            }
        }

        // 3) Xuất các dòng ra Output
        foreach (R r in cur)
        {
            Output0Buffer.AddRow();
            Output0Buffer.datekey = r.DateKey;
            Output0Buffer.stockkey = r.StockKey;
            Output0Buffer.industrykey = r.IndustryKey;
            Output0Buffer.eventkey = r.EventKey;
            Output0Buffer.volume = r.Volume;
            Output0Buffer.closeprice = r.Close;

            if (r.Open.HasValue) Output0Buffer.openprice = r.Open.Value; else Output0Buffer.openprice_IsNull = true;
            if (r.High.HasValue) Output0Buffer.highprice = r.High.Value; else Output0Buffer.highprice_IsNull = true;
            if (r.Low.HasValue) Output0Buffer.lowprice = r.Low.Value; else Output0Buffer.lowprice_IsNull = true;

            Output0Buffer.turnoverestbn = Clip(r.Turnover, 99999999999999m);

            if (r.HasPct)
            {
                Output0Buffer.pctchangecalc = Clip(r.Pct, 99999m);
                Output0Buffer.marketsentimentindex = r.Sentiment;
            }
            else
            {
                Output0Buffer.pctchangecalc_IsNull = true;
                Output0Buffer.marketsentimentindex_IsNull = true;
            }

            if (r.HasVola) Output0Buffer.volatilityindex = Clip(r.Vola, 99999m);
            else Output0Buffer.volatilityindex_IsNull = true;

            Output0Buffer.anomalycount = r.Anomaly;
            Output0Buffer.riskscore = Clip(r.Risk, 99999m);

            if (r.HasCrisis)
            {
                Output0Buffer.maxdrawdownpct = Clip(r.MaxDd, 99999m);
                Output0Buffer.troughpriceindex = Clip(r.Trough, 99999999999999m);
                Output0Buffer.totallossvalue = Clip(r.Loss, 99999999999999999m);
                if (r.Recovery.HasValue) Output0Buffer.recoverydays = r.Recovery.Value;
                else Output0Buffer.recoverydays_IsNull = true;
            }
            else
            {
                Output0Buffer.maxdrawdownpct_IsNull = true;
                Output0Buffer.troughpriceindex_IsNull = true;
                Output0Buffer.totallossvalue_IsNull = true;
                Output0Buffer.recoverydays_IsNull = true;
            }
        }

        cur.Clear();
    }
}