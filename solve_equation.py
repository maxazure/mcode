def solve_for_y(x):
    """
    解方程: 1 + x = y
    
    参数:
        x (int, float): 输入的x值
    
    返回:
        float: y的值
    """
    y = 1 + x
    return y

def main():
    """主函数，演示如何使用solve_for_y方法"""
    print("解方程: 1 + x = y")
    
    # 测试几个例子
    test_values = [0, 1, 2, -1, 3.5, -2.5]
    
    for x in test_values:
        y = solve_for_y(x)
        print(f"当 x = {x} 时, y = {y}")
    
    # 让用户输入自己的值
    try:
        user_input = input("\n请输入x的值 (按回车退出): ")
        if user_input.strip():
            x = float(user_input)
            y = solve_for_y(x)
            print(f"当 x = {x} 时, y = {y}")
    except ValueError:
        print("输入无效，请输入数字")
    except KeyboardInterrupt:
        print("\n程序结束")

if __name__ == "__main__":
    main()