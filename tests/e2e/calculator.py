import math


def calculate_orbit(initial_velocity, angle, gravity, drag_coefficient, air_density, rocket_mass, propellant_mass):
    # 将角度从度转换为弧度
    angle_rad = math.radians(angle)

    # 计算水平速度分量和垂直速度分量
    horizontal_velocity = initial_velocity * math.cos(angle_rad)
    vertical_velocity = initial_velocity * math.sin(angle_rad)

    # 初始总动量
    total_mass = rocket_mass + propellant_mass
    momentum = total_mass * initial_velocity

    # 轨道计算循环
    while True:
        # 计算空气阻力
        air_resistance = 0.5 * drag_coefficient * air_density * (horizontal_velocity**2 + vertical_velocity**2) * rocket_mass

        # 更新速度
        horizontal_velocity -= air_resistance * horizontal_velocity / total_mass
        vertical_velocity -= (gravity + air_resistance * vertical_velocity / total_mass) * (rocket_mass / total_mass)

        # 更新质量（假设推进剂按照恒定速率消耗）
        total_mass -= propellant_mass / 1000  # 假设每秒消耗1kg推进剂

        # 检查是否到达轨道或落地
        if vertical_velocity <= 0:
            break

    # 计算轨道半径和周期
    orbit_radius = math.sqrt(horizontal_velocity**2 / (2 * (gravity - air_resistance * horizontal_velocity / total_mass)))
    orbit_period = 2 * math.pi * math.sqrt(orbit_radius**3 / (gravity - air_resistance * horizontal_velocity / total_mass))

    return orbit_radius, orbit_period


def calculate_atmosphere_altitude(altitude, reference_sea_level=0):
    """
    计算海拔高度对应的大气层
    
    Args:
        altitude (float): 海拔高度 (km)
        reference_sea_level (float): 参考海平面高度 (km), 默认为0
    
    Returns:
        dict: 包含大气层信息和相关参数
    """
    # 大气层分界高度 (km)
    atmosphere_layers = {
        'troposphere': {'min': 0, 'max': 12, 'name': '对流层'},
        'stratosphere': {'min': 12, 'max': 50, 'name': '平流层'},
        'mesosphere': {'min': 50, 'max': 85, 'name': '中间层'},
        'thermosphere': {'min': 85, 'max': 600, 'name': '热层'},
        'exosphere': {'min': 600, 'max': float('inf'), 'name': '外层'}
    }
    
    # 调整高度为相对海平面
    adjusted_altitude = altitude - reference_sea_level
    
    # 确定所在大气层
    current_layer = None
    for layer_key, layer_info in atmosphere_layers.items():
        if layer_info['min'] <= adjusted_altitude < layer_info['max']:
            current_layer = layer_key
            break
    
    if current_layer is None:
        current_layer = 'exosphere'
    
    # 计算大气密度 (kg/m³) - 使用简化的指数模型
    sea_level_density = 1.225  # 海平面大气密度
    scale_height = 8.5  # 标高 (km)
    
    if adjusted_altitude < 0:
        air_density = sea_level_density * math.exp(adjusted_altitude / scale_height)
    elif adjusted_altitude < 100:
        air_density = sea_level_density * math.exp(-adjusted_altitude / scale_height)
    else:
        # 高层大气密度计算更复杂，这里使用简化模型
        air_density = sea_level_density * math.exp(-adjusted_altitude / scale_height) * 0.001
    
    # 计算温度 (K) - 使用标准大气模型
    if adjusted_altitude <= 11:
        temperature = 288.15 - 6.5 * adjusted_altitude
    elif adjusted_altitude <= 20:
        temperature = 216.65
    elif adjusted_altitude <= 32:
        temperature = 216.65 + 1.0 * (adjusted_altitude - 20)
    elif adjusted_altitude <= 47:
        temperature = 228.65 + 2.8 * (adjusted_altitude - 32)
    elif adjusted_altitude <= 51:
        temperature = 270.65
    elif adjusted_altitude <= 71:
        temperature = 270.65 - 2.8 * (adjusted_altitude - 51)
    elif adjusted_altitude <= 85:
        temperature = 214.65 - 2.0 * (adjusted_altitude - 71)
    else:
        temperature = 186.95
    
    # 计算气压 (Pa)
    if adjusted_altitude < 0:
        pressure = 101325 * math.exp(adjusted_altitude / scale_height)
    elif adjusted_altitude < 100:
        pressure = 101325 * math.exp(-adjusted_altitude / scale_height)
    else:
        pressure = 101325 * math.exp(-adjusted_altitude / scale_height) * 0.0001
    
    return {
        'altitude_km': altitude,
        'adjusted_altitude_km': adjusted_altitude,
        'layer': current_layer,
        'layer_name': atmosphere_layers[current_layer]['name'],
        'layer_range': f"{atmosphere_layers[current_layer]['min']}-{atmosphere_layers[current_layer]['max']} km",
        'air_density_kg_m3': max(air_density, 0),
        'temperature_k': max(temperature, 0),
        'pressure_pa': max(pressure, 0),
        'is_in_space': adjusted_altitude >= 100  # 卡门线以上为太空
    }


def calculate_atmospheric_layers_info():
    """
    返回所有大气层的详细信息
    
    Returns:
        dict: 所有大气层的信息
    """
    layers = {
        'troposphere': {
            'name': '对流层',
            'altitude_range': '0-12 km',
            'characteristics': '天气现象发生区域，温度随高度降低',
            'average_temperature': '288K (15°C) 到 217K (-56°C)',
            'contains_ozone': False
        },
        'stratosphere': {
            'name': '平流层',
            'altitude_range': '12-50 km',
            'characteristics': '臭氧层所在，温度随高度增加',
            'average_temperature': '217K (-56°C) 到 270K (-3°C)',
            'contains_ozone': True
        },
        'mesosphere': {
            'name': '中间层',
            'altitude_range': '50-85 km',
            'characteristics': '流星燃烧区域，温度随高度降低',
            'average_temperature': '270K (-3°C) 到 190K (-83°C)',
            'contains_ozone': False
        },
        'thermosphere': {
            'name': '热层',
            'altitude_range': '85-600 km',
            'characteristics': '极光发生区域，温度随高度急剧增加',
            'average_temperature': '190K (-83°C) 到 2000K+ (1727°C+)',
            'contains_ozone': False
        },
        'exosphere': {
            'name': '外层',
            'altitude_range': '600+ km',
            'characteristics': '大气层与太空的过渡区域，大气极其稀薄',
            'average_temperature': '2000K+ (1727°C+)',
            'contains_ozone': False
        }
    }
    
    return layers


def calculate_karman_line_altitude():
    """
    计算卡门线高度（太空边界）
    
    Returns:
        float: 卡门线高度 (km)
    """
    return 100.0  # 国际公认的卡门线高度


def calculate_ionosphere_layers(altitude):
    """
    计算电离层信息
    
    Args:
        altitude (float): 高度 (km)
    
    Returns:
        dict: 电离层信息
    """
    ionosphere_layers = {
        'D_layer': {'min': 60, 'max': 90, 'name': 'D层', 'frequency_range': '0.1-10 MHz'},
        'E_layer': {'min': 90, 'max': 150, 'name': 'E层', 'frequency_range': '1-10 MHz'},
        'F1_layer': {'min': 150, 'max': 250, 'name': 'F1层', 'frequency_range': '3-30 MHz'},
        'F2_layer': {'min': 250, 'max': 400, 'name': 'F2层', 'frequency_range': '5-30 MHz'}
    }
    
    current_layers = []
    for layer_key, layer_info in ionosphere_layers.items():
        if layer_info['min'] <= altitude < layer_info['max']:
            current_layers.append({
                'layer': layer_key,
                'name': layer_info['name'],
                'frequency_range': layer_info['frequency_range'],
                'altitude_range': f"{layer_info['min']}-{layer_info['max']} km"
            })
    
    return {
        'altitude_km': altitude,
        'in_ionosphere': len(current_layers) > 0,
        'layers': current_layers,
        'note': '电离层主要影响无线电波传播'
    }


def calculate_leo_orbital_parameters(altitude_km, inclination_deg=0, eccentricity=0):
    """
    计算近地轨道(LEO)卫星的轨道参数
    
    Args:
        altitude_km (float): 卫星轨道高度 (km)
        inclination_deg (float): 轨道倾角 (度)
        eccentricity (float): 轨道偏心率
    
    Returns:
        dict: 轨道参数
    """
    # 地球参数
    EARTH_RADIUS = 6371.0  # km
    EARTH_MASS = 5.972e24  # kg
    G = 6.67430e-11  # m^3 kg^-1 s^-2
    MU = 3.986004418e14  # m^3/s^2 (地球引力常数)
    
    # 转换单位
    altitude_m = altitude_km * 1000  # 转换为米
    earth_radius_m = EARTH_RADIUS * 1000
    
    # 轨道半径
    orbital_radius = earth_radius_m + altitude_m
    
    # 轨道速度 (圆轨道)
    orbital_velocity = math.sqrt(MU / orbital_radius)  # m/s
    
    # 轨道周期
    orbital_period = 2 * math.pi * math.sqrt(orbital_radius**3 / MU)  # 秒
    orbital_period_minutes = orbital_period / 60  # 分钟
    
    # 角速度
    angular_velocity = 2 * math.pi / orbital_period  # rad/s
    
    # 每日轨道圈数
    daily_orbits = 86400 / orbital_period
    
    # 地面轨迹速度 (考虑地球自转)
    earth_rotation_velocity = 2 * math.pi * EARTH_RADIUS * 1000 / 86400  # m/s
    ground_track_velocity = orbital_velocity - earth_rotation_velocity * math.cos(math.radians(inclination_deg))
    
    # 轨道能量
    specific_energy = -MU / (2 * orbital_radius)  # J/kg
    
    # 逃逸速度
    escape_velocity = math.sqrt(2 * MU / orbital_radius)  # m/s
    
    return {
        'altitude_km': altitude_km,
        'orbital_radius_km': orbital_radius / 1000,
        'orbital_velocity_km_s': orbital_velocity / 1000,
        'orbital_period_minutes': orbital_period_minutes,
        'orbital_period_hours': orbital_period_minutes / 60,
        'angular_velocity_rad_s': angular_velocity,
        'daily_orbits': daily_orbits,
        'ground_track_velocity_km_s': ground_track_velocity / 1000,
        'inclination_deg': inclination_deg,
        'eccentricity': eccentricity,
        'specific_energy_mj_kg': specific_energy / 1e6,
        'escape_velocity_km_s': escape_velocity / 1000,
        'is_leo': altitude_km < 2000,
        'orbit_type': 'LEO' if altitude_km < 2000 else 'MEO' if altitude_km < 35786 else 'GEO'
    }


def calculate_leo_ground_track(altitude_km, inclination_deg, initial_longitude=0, time_minutes=0):
    """
    计算LEO卫星的地面轨迹
    
    Args:
        altitude_km (float): 轨道高度 (km)
        inclination_deg (float): 轨道倾角 (度)
        initial_longitude (float): 初始经度 (度)
        time_minutes (float): 时间 (分钟)
    
    Returns:
        dict: 地面轨迹信息
    """
    # 获取轨道参数
    orbital_params = calculate_leo_orbital_parameters(altitude_km, inclination_deg)
    
    # 角速度
    angular_velocity = orbital_params['angular_velocity_rad_s']
    
    # 时间转换为秒
    time_seconds = time_minutes * 60
    
    # 卫星在轨道上的角度位置
    satellite_angle = angular_velocity * time_seconds  # rad
    satellite_angle_deg = math.degrees(satellite_angle) % 360
    
    # 地球自转角度
    earth_rotation_rate = 360 / (24 * 60)  # 度/分钟
    earth_rotation = earth_rotation_rate * time_minutes
    
    # 计算星下点位置
    subpoint_latitude = math.degrees(math.asin(math.sin(math.radians(inclination_deg)) * 
                                              math.sin(satellite_angle)))
    
    subpoint_longitude = (initial_longitude + earth_rotation + 
                         math.degrees(math.atan2(math.cos(math.radians(inclination_deg)) * 
                                               math.sin(satellite_angle),
                                               math.cos(satellite_angle)))) % 360
    if subpoint_longitude > 180:
        subpoint_longitude -= 360
    
    # 计算覆盖范围 (假设传感器视角角)
    sensor_angle = math.radians(30)  # 30度视角
    earth_radius = 6371.0  # km
    orbital_radius = earth_radius + altitude_km
    
    # 地心角
    central_angle = math.acos(earth_radius / orbital_radius * math.cos(sensor_angle))
    
    # 覆盖半径
    coverage_radius = earth_radius * central_angle  # km
    
    return {
        'time_minutes': time_minutes,
        'satellite_angle_deg': satellite_angle_deg,
        'subpoint_latitude_deg': subpoint_latitude,
        'subpoint_longitude_deg': subpoint_longitude,
        'earth_rotation_deg': earth_rotation,
        'coverage_radius_km': coverage_radius,
        'coverage_area_km2': math.pi * coverage_radius**2,
        'orbital_params': orbital_params
    }


def calculate_leo_trajectory_points(altitude_km, inclination_deg, num_points=100, time_span_minutes=90):
    """
    计算LEO卫星轨迹的多个点
    
    Args:
        altitude_km (float): 轨道高度 (km)
        inclination_deg (float): 轨道倾角 (度)
        num_points (int): 轨迹点数量
        time_span_minutes (float): 时间跨度 (分钟)
    
    Returns:
        list: 轨迹点列表
    """
    trajectory_points = []
    
    for i in range(num_points):
        time_minutes = (i / (num_points - 1)) * time_span_minutes
        point = calculate_leo_ground_track(altitude_km, inclination_deg, 
                                          initial_longitude=0, time_minutes=time_minutes)
        trajectory_points.append(point)
    
    return trajectory_points


def calculate_leo_coverage_analysis(altitude_km, sensor_angle_deg=30, revisit_time_minutes=0):
    """
    分析LEO卫星的覆盖能力
    
    Args:
        altitude_km (float): 轨道高度 (km)
        sensor_angle_deg (float): 传感器视角角 (度)
        revisit_time_minutes (float): 重访时间 (分钟)
    
    Returns:
        dict: 覆盖分析结果
    """
    orbital_params = calculate_leo_orbital_parameters(altitude_km)
    
    # 地球参数
    earth_radius = 6371.0  # km
    orbital_radius = earth_radius + altitude_km
    
    # 传感器参数
    sensor_angle_rad = math.radians(sensor_angle_deg)
    
    # 计算覆盖参数
    # 修正条件：传感器能够看到地球的条件
    max_earth_angle = math.asin(earth_radius / orbital_radius)
    if sensor_angle_rad <= max_earth_angle:
        # 地心角
        central_angle = math.acos(earth_radius / orbital_radius * math.cos(sensor_angle_rad))
        
        # 覆盖半径
        coverage_radius = earth_radius * central_angle
        
        # 覆盖面积
        coverage_area = 2 * math.pi * earth_radius**2 * (1 - math.cos(central_angle))
        
        # 地球表面积
        earth_surface_area = 4 * math.pi * earth_radius**2
        
        # 覆盖百分比
        coverage_percentage = (coverage_area / earth_surface_area) * 100
        
        # 瞬时覆盖
        instantaneous_coverage = coverage_area
        
        # 每日覆盖（考虑轨道圈数）
        daily_coverage = instantaneous_coverage * orbital_params['daily_orbits']
        
        # 重访时间计算
        if revisit_time_minutes == 0:
            # 默认重访时间为轨道周期
            revisit_time = orbital_params['orbital_period_minutes']
        else:
            revisit_time = revisit_time_minutes
        
        # 覆盖频率
        coverage_frequency = 1440 / revisit_time  # 每日覆盖次数
        
    else:
        # 传感器无法看到地球
        central_angle = 0
        coverage_radius = 0
        coverage_area = 0
        coverage_percentage = 0
        instantaneous_coverage = 0
        daily_coverage = 0
        revisit_time = float('inf')
        coverage_frequency = 0
    
    return {
        'altitude_km': altitude_km,
        'sensor_angle_deg': sensor_angle_deg,
        'central_angle_rad': central_angle,
        'central_angle_deg': math.degrees(central_angle),
        'coverage_radius_km': coverage_radius,
        'instantaneous_coverage_km2': instantaneous_coverage,
        'daily_coverage_km2': daily_coverage,
        'coverage_percentage': coverage_percentage,
        'revisit_time_minutes': revisit_time,
        'coverage_frequency_per_day': coverage_frequency,
        'orbital_params': orbital_params
    }


def calculate_leo_communication_window(altitude_km, ground_station_lat, ground_station_lon, 
                                     min_elevation_deg=10, time_hours=24):
    """
    计算LEO卫星与地面站的通信窗口
    
    Args:
        altitude_km (float): 轨道高度 (km)
        ground_station_lat (float): 地面站纬度 (度)
        ground_station_lon (float): 地面站经度 (度)
        min_elevation_deg (float): 最小仰角 (度)
        time_hours (float): 计算时间范围 (小时)
    
    Returns:
        dict: 通信窗口信息
    """
    orbital_params = calculate_leo_orbital_parameters(altitude_km)
    
    # 转换为弧度
    ground_lat_rad = math.radians(ground_station_lat)
    ground_lon_rad = math.radians(ground_station_lon)
    min_elevation_rad = math.radians(min_elevation_deg)
    
    # 地球参数
    earth_radius = 6371.0  # km
    orbital_radius = orbital_params['orbital_radius_km'] * 1000  # m
    
    # 计算最大地心角（基于最小仰角）
    max_central_angle = math.acos(earth_radius / orbital_radius * math.cos(min_elevation_rad)) - min_elevation_rad
    
    # 通信窗口
    communication_windows = []
    total_comm_time = 0
    
    # 模拟一天内的轨道
    time_step = 1  # 分钟
    for minute in range(0, int(time_hours * 60), time_step):
        # 计算卫星位置
        satellite_pos = calculate_leo_ground_track(altitude_km, 45,  # 假设45度倾角
                                                  ground_station_lon, minute)
        
        # 计算地心角
        lat_diff = math.radians(satellite_pos['subpoint_latitude_deg'] - ground_station_lat)
        lon_diff = math.radians(satellite_pos['subpoint_longitude_deg'] - ground_station_lon)
        
        central_angle = math.acos(math.sin(ground_lat_rad) * 
                                 math.sin(math.radians(satellite_pos['subpoint_latitude_deg'])) +
                                 math.cos(ground_lat_rad) * 
                                 math.cos(math.radians(satellite_pos['subpoint_latitude_deg'])) *
                                 math.cos(lon_diff))
        
        # 计算仰角
        elevation = math.degrees(math.atan2(math.cos(central_angle) - earth_radius/orbital_radius,
                                           math.sin(central_angle)))
        
        # 检查是否在通信窗口内
        if elevation >= min_elevation_deg:
            if not communication_windows or len(communication_windows[-1]) == 2:
                # 新窗口开始
                communication_windows.append([minute, minute])
            else:
                # 延长当前窗口
                communication_windows[-1][1] = minute
            total_comm_time += time_step
    
    # 转换窗口时间格式
    windows_formatted = []
    for window in communication_windows:
        start_time = window[0] / 60  # 转换为小时
        end_time = window[1] / 60
        duration = window[1] - window[0]  # 分钟
        windows_formatted.append({
            'start_hour': start_time,
            'end_hour': end_time,
            'duration_minutes': duration,
            'start_time_str': f"{int(start_time):02d}:{int((start_time % 1) * 60):02d}",
            'end_time_str': f"{int(end_time):02d}:{int((end_time % 1) * 60):02d}"
        })
    
    return {
        'altitude_km': altitude_km,
        'ground_station': {
            'latitude_deg': ground_station_lat,
            'longitude_deg': ground_station_lon
        },
        'min_elevation_deg': min_elevation_deg,
        'time_hours': time_hours,
        'communication_windows': windows_formatted,
        'num_windows': len(windows_formatted),
        'total_communication_time_minutes': total_comm_time,
        'average_window_duration_minutes': total_comm_time / len(windows_formatted) if windows_formatted else 0,
        'communication_efficiency': (total_comm_time / (time_hours * 60)) * 100,
        'orbital_params': orbital_params
    }