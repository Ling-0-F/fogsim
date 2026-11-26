"""Draw the full-budget GPU timing curves from the measured event and device logs."""

import argparse
from bisect import bisect_left
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

from .summarize import read_csv


BLUE = "#176A80"
ORANGE = "#B95020"
GRAY = "#52626C"
INK = "#192B36"


def values(rows, key):
    return [float(row[key]) for row in rows]


def use_font(path):
    if path:
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()
    else:
        family = "Noto Sans CJK SC"
    plt.rcParams.update(
        {
            "font.family": [family, "sans-serif"],
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": INK,
            "axes.edgecolor": "#C4D0D4",
            "xtick.color": GRAY,
            "ytick.color": GRAY,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "axes.unicode_minus": False,
        }
    )


def plot(root, font=None):
    use_font(font)
    report = json.loads((root / "summary.json").read_text())
    events = read_csv(root / "timeline.csv")
    generations = read_csv(root / "generations.csv")
    rates = read_csv(root / "throughput.csv")
    calibration = read_csv(root / "scaling.csv")
    device = [r for r in read_csv(root / "search/device.csv") if r["busy_pct"] and not r["error"]]
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.5))
    fig.subplots_adjust(left=0.082, right=0.917, top=0.825, bottom=0.105, wspace=0.32, hspace=0.57)
    run = json.loads((root / "search/run.json").read_text())
    name = run.get("gpu_name", "S4000").removeprefix("NVIDIA GeForce ").removeprefix("MTT ")
    fig.text(0.082, 0.946, f"一张 {name} 的 30 次独立搜索", fontsize=22, weight="bold")
    total = round(report["wall_s"])
    fig.text(
        0.083,
        0.900,
        f"Small · 单设备    |    1,000 个体 × 51 代    |    {report['parallel']} 路并发"
        f"    |    端到端 {total // 60} 分 {total % 60:02d} 秒    |    {report['unique_train']:,} 次训练评价",
        fontsize=11,
        color=GRAY,
    )
    for ax in axes.flat:
        ax.grid(axis="y", color="#E3E9EC", lw=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=3)
    a, b, c, d = axes.flat
    titles = ("累计完成进度", "每一代花了多少时间", "训练吞吐与 GPU 忙碌率", "同一组种子的并发校准")
    for ax, title in zip(axes.flat, titles, strict=True):
        ax.set_title(title, loc="left", fontsize=14, pad=10, weight="bold")

    minutes = [s / 60 for s in values(events, "elapsed_s")]
    a.step(
        minutes,
        [n * 100 / report["unique_train"] for n in values(events, "cumulative_train")],
        where="post",
        color=BLUE,
        lw=2.1,
        label="训练评价",
    )
    a.step(
        minutes,
        [n * 100 / 30 for n in values(events, "completed_trials")],
        where="post",
        color=ORANGE,
        lw=1.5,
        label="完成全部流程的试次",
    )
    half = report["train_milestone_s"]["50"] / 60
    a.plot(half, 50, "o", color=BLUE, ms=5)
    a.annotate(
        f"{half:.1f} 分钟完成一半训练",
        (half, 50),
        xytext=(-9, 12),
        textcoords="offset points",
        ha="right",
        fontsize=8.4,
        color=BLUE,
    )
    a.set(xlim=(0, minutes[-1]), ylim=(0, 105), xlabel="正式搜索经过时间（分钟）", ylabel="完成比例（%）")
    a.legend(loc="upper left", frameon=False, fontsize=9)

    gen = values(generations, "generation")
    b.fill_between(
        gen,
        values(generations, "wall_p10_s"),
        values(generations, "wall_p90_s"),
        color="#D8EBEE",
        label="试次间第 10–90 百分位",
    )
    b.plot(gen, values(generations, "wall_median_s"), color=BLUE, lw=2, label="单代墙钟中位数")
    b.plot(
        gen,
        values(generations, "kernel_median_s"),
        color=ORANGE,
        lw=1.5,
        linestyle="--",
        label="设备内核计时中位数",
    )
    b.set(xlim=(1, 51), ylim=(0, None), xlabel="代数", ylabel="每代用时（秒）")
    b.set_xticks([1, 10, 20, 30, 40, 51])
    b.legend(loc="upper left", frameon=False, fontsize=8.8)

    rates = [r for r in rates if float(r["elapsed_s"]) >= 30]
    c.plot(
        [s / 60 for s in values(rates, "elapsed_s")],
        values(rates, "trailing_train_per_s"),
        color=BLUE,
        lw=1.55,
        label="训练评价 / 秒",
    )
    c.set(xlim=(0, minutes[-1]), ylim=(0, None), xlabel="正式搜索经过时间（分钟）", ylabel="训练评价 / 秒")
    c.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    busy_axis = c.twinx()
    busy_axis.spines["right"].set_visible(True)
    sample_t, busy = values(device, "elapsed_s"), values(device, "busy_pct")
    smooth_times, smooth_busy = [], []
    for i, end in enumerate(sample_t):
        if end >= 30:
            first = bisect_left(sample_t, end - 30)
            smooth_times.append(end / 60)
            smooth_busy.append(sum(busy[first : i + 1]) / (i - first + 1))
    busy_axis.plot(smooth_times, smooth_busy, color=ORANGE, lw=1.2, linestyle="--")
    busy_axis.set_ylim(0, 105)
    busy_axis.set_ylabel("设备忙碌率（%）", color=ORANGE, labelpad=3)
    busy_axis.tick_params(axis="y", colors=ORANGE, length=3)
    c.yaxis.label.set_color(BLUE)
    c.tick_params(axis="y", colors=BLUE)

    cohorts = sorted({int(row["count"]) for row in calibration})
    for idx, count in enumerate(cohorts):
        subset = sorted(
            (row for row in calibration if int(row["count"]) == count), key=lambda r: int(r["parallel"])
        )
        x, y = values(subset, "parallel"), values(subset, "unique_per_s")
        d.plot(
            x,
            y,
            color=(BLUE, ORANGE)[idx],
            marker=("o", "s")[idx],
            ms=6,
            lw=2,
            label=f"相同 {count} 个种子",
        )
        for lane, rate in zip(x, y, strict=True):
            neighbors = [float(row["unique_per_s"]) for row in calibration if int(row["parallel"]) == lane]
            offset = 8 if idx == 0 else -16
            if len(neighbors) > 1:
                offset = 8 if rate == max(neighbors) else -16
            d.annotate(
                f"{rate:,.0f}",
                (lane, rate),
                xytext=(0, offset),
                textcoords="offset points",
                ha="center",
                color=(BLUE, ORANGE)[idx],
                fontsize=9,
            )
    xvals = sorted({int(row["parallel"]) for row in calibration})
    yrates = values(calibration, "unique_per_s")
    d.set_xticks(xvals)
    d.set(
        xlim=(xvals[0] - 0.35, xvals[-1] + 0.35),
        ylim=(min(yrates) * 0.94, max(yrates) * 1.07),
        xlabel="同时使用这张卡的搜索进程数",
        ylabel="平均训练评价 / 秒",
    )
    d.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    d.yaxis.set_major_locator(MaxNLocator(5))
    if len(cohorts) > 1:
        d.legend(loc="upper left", fontsize=9, frameon=False)
    fig.text(
        0.082,
        0.032,
        "训练评价按每代去重。逐代分位数来自 30 个试次。吞吐与设备忙碌率均取过去 30 秒。"
        "并发校准含验证、测试及写盘，独立于正式搜索计时。",
        fontsize=9,
        color=GRAY,
    )
    for extension in ("png", "pdf"):
        fig.savefig(root / f"timing-curves.{extension}", dpi=170, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--font", type=Path, help="Chinese OpenType font, e.g. Noto Sans CJK SC")
    args = parser.parse_args()
    plot(args.folder, args.font)
