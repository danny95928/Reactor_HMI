import pandas as pd
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score


def train():
    # ==========================================
    # 1. 配置路径
    # ==========================================
    # 获取当前脚本所在的目录 (假设脚本在项目根目录下运行)
    base_dir = os.getcwd()

    # 根据您提供的路径拼接 CSV 文件的绝对路径
    # 注意：这里使用了 os.path.join 自动处理 Windows/Linux 路径分隔符
    csv_file = os.path.join(base_dir, "ui", "modules", "dataset", "reactor_process_data.csv")

    # 模型保存路径 (保存在根目录，方便主程序调用)
    model_path = os.path.join(base_dir, "reactor_fault_model.pkl")
    scaler_path = os.path.join(base_dir, "reactor_scaler.pkl")

    # ==========================================
    # 2. 读取数据
    # ==========================================
    print(f"📂 正在尝试读取数据: {csv_file}")

    if not os.path.exists(csv_file):
        print("❌ 错误：找不到 CSV 文件！")
        print("   请确认文件路径是否正确，或者文件是否已生成。")
        return

    try:
        df = pd.read_csv(csv_file)
        print(f"✅ 读取成功，共 {len(df)} 条数据")
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return

    # ==========================================
    # 3. 训练模型
    # ==========================================
    feature_cols = ['Speed_Raw', 'Temp_Raw', 'Viscosity_Raw', 'MassFrac_Raw', 'MixTime_Raw']

    # 检查列是否存在
    if not set(feature_cols).issubset(df.columns):
        print(f"❌ 数据集缺少必要的列。需要: {feature_cols}")
        return

    X = df[feature_cols]
    y = df['Code_Quality']

    # 划分与标准化
    print("⚙️ 正在划分数据集并标准化...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 训练
    print("🚀 正在训练随机森林模型...")
    clf = RandomForestClassifier(n_estimators=50, random_state=42)
    clf.fit(X_train_scaled, y_train)

    # 评估
    score = clf.score(X_test_scaled, y_test)
    print(f"🏆 模型准确率: {score:.2%}")

    # ==========================================
    # 4. 保存模型
    # ==========================================
    print("💾 正在保存模型文件...")
    try:
        joblib.dump(clf, model_path)
        joblib.dump(scaler, scaler_path)
        print(f"✅ 模型已保存至: {model_path}")
        print(f"✅ 标准化参数已保存至: {scaler_path}")
    except Exception as e:
        print(f"❌ 保存模型失败: {e}")


if __name__ == "__main__":
    train()