import numpy as np
from itertools import combinations
import subprocess
import networkx as nx
import math
from scipy.spatial import Delaunay
import gurobipy as gp
from scipy.spatial import Voronoi,voronoi_plot_2d
import matplotlib.pyplot as plt
import json



#根据坐标创建矩阵
def dis_mat(coord):
    #获取个数
    n = len(coord)

    #距离矩阵
    mat = np.zeros((n,n))
    #所有三角形组合
    combs = combinations(range(0,n),2)

    for comb in combs:
        #计算欧氏距离
        dij = np.sqrt( ( coord[comb[0],0] - coord[comb[1],0] )**2   +   
                        (coord[comb[0],1] - coord[comb[1],1] )**2  )
        
        #取整
        dij = round(dij)
        #存入
        mat[ comb[0], comb[1] ] = dij

    #补全矩阵
    for i in range(n):
        for j in range(n):
            if i > j:
                mat[i,j] = mat[j,i]

    return mat

#通过delaunay计算lamuda，返回元组 0：最大lamuda  1：每个城市最大lamuda列表  2:lamuda最大时左右城市列表  
def delaunay(dis_mat, cities_coord, seg1 = None, nei2 = None, seg3 = None) -> tuple:

    # 进行德劳内三角剖分
    tri = Delaunay(cities_coord)

    # 创建图对象
    G = nx.Graph()

    # 将剖分中的边添加到图中,每个simplex是三角形
    for simplex in tri.simplices:
        edges = [(simplex[i], simplex[j]) for i in range(3) for j in range(i+1, 3)]
        G.add_edges_from(edges)

    #添加线段对应的边
    if seg1 is not None:
        #变为元组（似乎不变也行）
        #edges = [ (edge[0],edge[1]) for edge in add_edges]
        G.add_edges_from(seg1)    

    #如果添加邻居的邻居
    if nei2 is not None:
        G.add_edges_from(nei2)

    if seg3 is not None:
        G.add_edges_from(seg3)


    #画出三角分割(如果增加了边就不是三角分割)
    # pos = {i: cities_coord[i] for i in range(cities_coord.shape[0])}
    # nx.draw(G,pos, with_labels=True, node_size=300, node_color='skyblue')
    # plt.show()


    ######################计算lamuda######################
    #记录每个城市的最大lamuda
    max_lamuda = []

    #记录每个城市最大lamuda时左右城市索引
    left_and_right_index_for_every_city = []


    #遍历每个节点城市，i为城市索引
    for i in range(cities_coord.shape[0]):
        #生成组合列表
        neighbors =  list(combinations(list(G.neighbors(i)),2) )

        #当前最大lamuda
        temp_max = 0

        #当前最大lamuda左右组合,元组
        temp_left_right = ()
    
        #遍历每个组合，计算lamuda
        for neighbor in neighbors:

            #根据矩阵计算
            current_lamuda = 0.5 * (  dis_mat[i,neighbor[0] ] +  dis_mat[i,neighbor[1] ] )
            
            #向下取整!!!!
            current_lamuda = math.floor(current_lamuda)

            #保存最大lamuda
            if current_lamuda > temp_max:
                temp_max = current_lamuda
                #并且保存当前组合
                temp_left_right = neighbor

        #保存
        max_lamuda.append(temp_max)
        #保存左右索引
        left_and_right_index_for_every_city.append(temp_left_right)

    #不能刚好等于，要稍微大一点
    max_lamuda = [ temp + 1 for temp in max_lamuda]    
        
    return max(max_lamuda) , max_lamuda  , G  ,G.number_of_edges()

#基于voronoi图加边，一个线段
def edges_add_seg1(cities_coord):
    # 创建 Voronoi 图
    vor = Voronoi(cities_coord)
    # voronoi_plot_2d(vor)
    # plt.show()

    #平面分界线交点的坐标
    coord_inter = vor.vertices

    #每条分界线两个端点索引（平面分界线交点的索引）
    ridge = vor.ridge_vertices

    #把无穷远的分界线去除(保留有限ridge)
    ridge = [node for node in ridge if -1 not in node]

    #计算每个有限ridge长度
    ridge_len = []
    for node in ridge:
        dis = np.sqrt( (coord_inter[node[0]][0] - coord_inter[node[1]][0])**2+ 
                       (coord_inter[node[0]][1] - coord_inter[node[1]][1])**2 )
        
        ridge_len.append(dis)

    #设定阈值
    threshold = max(ridge_len)

    #筛选要变成点的边
    ridge_to_node = [node for node in ridge if ridge_len[ridge.index(node)] <= threshold]

    #所有的面(分界线端点索引)
    regions = vor.regions

    #等待连接的region
    regions_to_connect = []
    for node in ridge_to_node:
        #两个端点所属的面
        node1 = []
        node2 = []
        for region in regions:
            if node[0] in region:
                node1.append(regions.index(region) )
            if node[1] in region:
                node2.append(regions.index(region) )
                pass

        #转换为集合
        node1 = set(node1)
        node2 = set(node2)

        #取互不相交的部分(避免重复)
        #temp = (node1 - node2) | (node2 - node1)
        temp = node1.symmetric_difference(node2)

        if temp not in regions_to_connect:
            regions_to_connect.append(temp) 


    #原始点所属region
    regions = vor.point_region

    #需要连接的原始点
    nodes_to_connect = []

    for Region in regions_to_connect:
        #存储对应的原始点索引
        temp = []
        for region in Region:
            temp.append(np.where(regions == region)[0][0])
            pass
        nodes_to_connect.append(temp)
    
    nodes_to_connect = list(map(lambda x : tuple(x),nodes_to_connect))
    #print(nodes_to_connect)
    return nodes_to_connect

#再次基于voronoi加边，邻居的邻居
def edges_add_nei2(cities_coord):
    vor = Voronoi(cities_coord)

    #voronoi边，包括射线
    ridge = vor.ridge_vertices

    regions = vor.regions
    point_region = vor.point_region

    #每个节点的邻接关系，种子节点顺序
    neighbor_list = []
    for node in range(cities_coord.shape[0]):
        #当前种子节点对应区域索引
        current_region_index = point_region[node]

        #当前区域所对应的voronoi顶点
        current_region_voronoi_vertex = regions[current_region_index]
        
        #与当前区域相邻的区域的索引
        neighbor_region = set()
        for vonoroi_vertex in current_region_voronoi_vertex:
            for region in regions:
                if vonoroi_vertex in region:
                    neighbor_region.add(regions.index(region))
        
        #去除自己
        neighbor_region.discard(current_region_index)
        #加入列表
        neighbor_list.append(neighbor_region)

    #print(neighbor_list)

    #计算需要连接的边
    edge_to_connect = []
    for index in range(cities_coord.shape[0]):
        #当前区域的邻居
        region = neighbor_list[index]

        #当前区域的索引
        region_index = point_region[index]
        
        #遍历每个邻居
        for neighbor in region:
            
            #取得邻居的邻居，居然不能直接改动，得复制
            neighbors = neighbor_list[np.where(point_region == neighbor)[0][0]].copy()

            #从中删除当前种子节点的区域
            neighbors.discard(region_index)
            

            #遍历每个邻居的邻居
            for sub_neighbor in neighbors:
                temp = {index,np.where(point_region == sub_neighbor)[0][0]}
                if temp not in edge_to_connect:
                    edge_to_connect.append(temp)
                

    edge_to_connect = list(map(lambda x : tuple(x),edge_to_connect))
    
    return edge_to_connect

#三个线段加边
def edges_add_seg3(cities_coord):
    # 创建 Voronoi 图
    vor = Voronoi(cities_coord)

    #voronoi顶点的坐标
    vor_vertices = vor.vertices
    
    #每条ridge两个端点索引（voronoi顶点的索引）
    ridges = vor.ridge_vertices
    
    #把无穷远的分界线去除(保留有限ridge)
    ridges_without_infinite = [vertex for vertex in ridges if -1 not in vertex]
   
    #带有voronoi顶点索引的区域
    regions_with_voronoi_vertex = vor.regions
   
    #带有母点索引的区域
    regions_with_mother_point = list(vor.point_region)
    
    #需要被连接的边
    edges_to_connect = []

    #遍历每个vor_vertex
    connect_relation = []
    for vor_vertex in range(len(vor_vertices)):

        #与各个voronoi顶点相邻的voronoi顶点
        temp = [vertex for ridge in ridges 
                          if vor_vertex in ridge
                          for vertex in ridge
                          if vertex != vor_vertex]
        
        connect_relation.append(temp)
        

    #遍历每个voronoi顶点
    for vor_vertex in range(len(vor_vertices)):
        #第1层（不包含-1，且不会包含自己）
        level_1 = [vertex for vertex in connect_relation[vor_vertex] 
                   if vertex != -1]

        #第2层
        level_2 = []
        for level_1_vertex in level_1:
            temp = [vertex for vertex in connect_relation[level_1_vertex]
                    if vertex not in (-1, vor_vertex)]
            level_2.append(temp)

        #第3层,列表为空代表不存在
        level_3 = []
        for index, level_2_vertices in enumerate(level_2):   
            temp_2 = [] 
            for level_2_vertex in level_2_vertices:
                #每个第2层的连接    
                temp_1 = [vertex for vertex in connect_relation[level_2_vertex]
                        if vertex not in (-1, vor_vertex, level_1[index])] 
                temp_2.append(temp_1)
            level_3.append(temp_2)

        #路线
        routes = [(vor_vertex, level_1_vertex, level_2_vertex, level_3_vertex)
                 for index_level_1, level_1_vertex in enumerate(level_1)
                 for index_level_2, level_2_vertex in enumerate(level_2[index_level_1])
                 for level_3_vertex in level_3[index_level_1][index_level_2]]
        # print()
        # print(routes)
        #复杂写法
        # for index_level_1, level_1_vertex in enumerate(level_1):
        #     for index_level_2, level_2_vertex in enumerate(level_2[index_level_1]):
        #         for level_3_vertex in level_3[index_level_1][index_level_2]:
        #             print(vor_vertex,level_1_vertex, level_2_vertex, level_3_vertex)

        #遍历每一段路径
        for route in routes:

            vertex_1_regions = [vertex_1_region 
                                for vertex_1_region in regions_with_voronoi_vertex
                                if route[0] in vertex_1_region]
            vertex_2_regions = [vertex_2_region 
                                for vertex_2_region in regions_with_voronoi_vertex
                                if route[1] in vertex_2_region]
            vertex_3_regions = [vertex_3_region 
                                for vertex_3_region in regions_with_voronoi_vertex
                                if route[2] in vertex_3_region]
            vertex_4_regions = [vertex_4_region 
                                for vertex_4_region in regions_with_voronoi_vertex
                                if route[3] in vertex_4_region]
            

            #获取每个voronoi顶点相关联的region的索引
            vertex_1_region_index = []
            vertex_2_region_index = []
            vertex_3_region_index = []
            vertex_4_region_index = []
            for vertex_1_region, vertex_2_region, vertex_3_region, vertex_4_region \
                in zip(vertex_1_regions,vertex_2_regions,vertex_3_regions,vertex_4_regions):
                vertex_1_region_index.append(regions_with_voronoi_vertex.index(vertex_1_region))
                vertex_2_region_index.append(regions_with_voronoi_vertex.index(vertex_2_region))
                vertex_3_region_index.append(regions_with_voronoi_vertex.index(vertex_3_region))
                vertex_4_region_index.append(regions_with_voronoi_vertex.index(vertex_4_region))



            #front 前面两个点 route[0] route[1], back 后面两个点 route[2] route[3],region_list里一定会有两个元素
            front_region_list = list(set(vertex_1_region_index).symmetric_difference(set(vertex_2_region_index))) 
            back_region_list = list(set(vertex_3_region_index).symmetric_difference(set(vertex_4_region_index)))
            
            #得到需要连接的两个region的索引
            front_set = set()
            back_set = set()
            for front, back in zip(front_region_list, back_region_list):
                if route[0] in regions_with_voronoi_vertex[front]:
                    front_set.add(front)
                if route[3] in regions_with_voronoi_vertex[back]:
                    back_set.add(back)

            #去重
            set_of_this_route = front_set.union(back_set)

            #只有长度为2的才需要连接
            if len(set_of_this_route) == 2:
                edges_to_connect.append((regions_with_mother_point.index(set_of_this_route.pop()),
                                            regions_with_mother_point.index(set_of_this_route.pop())))
               

    return edges_to_connect


#画出最佳路径图
def optimal_tour_graph(num_city):
    #从文件读取最佳路径
    with open(f'complete_graph/tour/random{num_city}.txt','r') as file:
        #读取tour
        tour = file.readlines()[6:-2]

        #格式转换，去除换行符
        tour = list(map(lambda x: int(x) - 1, tour))

    #创建图
    G = nx.Graph()

    #添加边
    edges = [(tour[i], tour[(i+1) % num_city]) for i in range(num_city)]
    G.add_edges_from(edges)

    return G

#判断是否是子图，只考虑边(最优路径图，添加边的图)
def is_subgraph(G_optimal,G_add_edges):

    #边的格式转换
    G_optimal_edge_list = list(map(lambda x: set(x),list(G_optimal.edges)))
    G_add_edges_list = list(map(lambda x: set(x),list(G_add_edges.edges)))
    
    #判断optimal的边是否在add_edges里，如果不在则保留
    not_in_list = list(filter(lambda x : x not in G_add_edges_list, G_optimal_edge_list))
    #print(not_in_list)
    #列表为空时是子图
    return not not_in_list, not_in_list

#判断是否是子图
def is_subgraph2(G_optimal, G_add_de):
    # 边的格式转换
    G_optimal_edge_set = set(map(frozenset, G_optimal.edges()))
    G_add_de_edge_set = set(map(frozenset, G_add_de.edges()))
    
    # 判断G_optimal的每条边是否都在G_add_de中
    not_in_set = G_optimal_edge_set - G_add_de_edge_set
    print(not_in_set)
    # 如果not_in_set为空，说明G_optimal是G_add_de的子图
    return len(not_in_set) == 0, not_in_set

#生成包含各类数据的字典以供查阅,并且dump到json
def creat_dump_data_dic():
    dic = {}
    for i in range(5,101):
        print(i)
        ins = instance(i)
        dic[f'{i}'] = {'de_edges':ins.de_edges,
                       'seg1_edges':ins.seg1_edges,
                       'seg1_nei2_edges':ins.seg1_nei2_edges,
                       'seg1_nei2_seg3_edges':ins.seg1_nei2_seg3_edges,

                       'de_lambda':ins.de_lambda,
                       'seg1_lambda':ins.seg1_lambda,
                       'seg1_nei2_lambda':ins.seg1_nei2_lambda,
                       'seg1_nei2_seg3_lambda':ins.seg1_nei2_seg3_lambda,

                       'de_is_subgraph':is_subgraph(ins.graph_optimal_tour,ins.graph_de)[0],
                       'seg1_is_subgraph':is_subgraph(ins.graph_optimal_tour,ins.graph_seg1)[0],
                       'seg1_nei2_is_subgraph':is_subgraph(ins.graph_optimal_tour,ins.graph_seg1_nei2)[0],
                       'seg1_nei2_seg3_is_subgraph':is_subgraph(ins.graph_optimal_tour,ins.graph_seg1_nei2_seg3)[0]}
    
    json.dump(dic,open('data.json','w'),indent=4)


#读取数据json
def read_json():
    with open('data.json','r') as file:
        dic = json.load(file)
    return dic

#基于原有距离矩阵生成missing edges的距离矩阵，用999999
def creat_dis_mat_missing_edges(n,G_add_edges,dis_mat):
    #完全图的边
    complete_edges = [{i, j} for i in range(n) for j in range(i+1,n)]
    
    #存在的边
    exist_edges = list(map(lambda x:set(x), G_add_edges.edges()))
    
    #求基于完全图消失的边
    missing_edges = list(filter(lambda x :x not in exist_edges, complete_edges))
    
    #创建基于消失边的距离矩阵
    for edge in missing_edges:
        temp = list(edge)
        dis_mat[temp[0],temp[1]] = 999999
        dis_mat[temp[1],temp[0]] = 999999
        
    return dis_mat

#比较最优路径是否一致，完全图的最优路径 和 非完全图的最优路径
def compare_tour(n):

    with open(f'complete_graph/tour/random{n}.txt','r') as file:
        tour_complete = file.readlines()[6:-2]

    with open(f'graph_missing_edges/tour/random{n}.txt','r') as file:
        tour_missing = file.readlines()[6:-2]

    tour_complete = list(map(lambda x:int(x),tour_complete))
    tour_missing = list(map(lambda x:int(x),tour_missing)) 

    #print(tour_complete,tour_missing)  
    return tour_complete , tour_missing 


class instance():
    def __init__(self,n):
        #城市个数
        self.n = n
        #城市坐标
        #随机数种子选取 确保每次生成的一致
        np.random.seed(self.n)
        self.coord = np.random.random((self.n,2)) * 100
        #距离矩阵
        self.mat = dis_mat(self.coord)

        #为了画图的参数
        self.graph_pos = {i: self.coord[i] for i in range(self.n)}

        #最优路径图
        self.graph_optimal_tour = optimal_tour_graph(self.n)

        #普通的delauny lambda
        result = delaunay(self.mat,self.coord)
        self.de_lambda = result[0] 
        self.de_lambda_list = result[1]
        self.graph_de = result[2]   #德劳内三角分割图
        self.de_edges = result[3]

        #基于voronoi线段添加边的delauny lambda
        result = delaunay(self.mat, self.coord, 
                          seg1 = edges_add_seg1(self.coord))
        self.seg1_lambda = result[0] 
        self.seg1_lambda_list = result[1]
        self.graph_seg1 = result[2]   #基于德劳内三角分割加线段对应边的图
        self.seg1_edges = result[3]

        #基于voronoi添加一次线段后，再添加邻居的邻居
        result = delaunay(self.mat, self.coord, 
                          seg1 = edges_add_seg1(self.coord),
                          nei2 = edges_add_nei2(self.coord))
        self.seg1_nei2_lambda = result[0] 
        self.seg1_nei2_lambda_list = result[1]
        self.graph_seg1_nei2 = result[2]   #加邻居的邻居
        self.seg1_nei2_edges = result[3]


        #基于voronoi只添加邻居的邻居
        result = delaunay(self.mat,self.coord,
                          nei2 = edges_add_nei2(self.coord))
        self.nei2_lambda = result[0] 
        self.nei2_lambda_list = result[1]
        self.graph_nei2 = result[2]   
        self.nei2_edges = result[3]

        #seg3加边
        result = delaunay(self.mat,self.coord,
                          seg1 = edges_add_seg1(self.coord),
                          nei2 = edges_add_nei2(self.coord),
                          seg3 = edges_add_seg3(self.coord))
        self.seg1_nei2_seg3_lambda = result[0] 
        self.seg1_nei2_seg3_lambda_list = result[1]
        self.graph_seg1_nei2_seg3 = result[2]   
        self.seg1_nei2_seg3_edges = result[3]


        #基于非完全图的距离矩阵
        #Python中的可变类型在作为参数传递给函数时，因为传递的是对象的引用而不是其副本。
        #当你在函数内部修改这些可变对象时，外部的原始对象也会被修改。
        self.mat_missing_edges = creat_dis_mat_missing_edges(self.n,self.graph_seg1_nei2,self.mat.copy())

    #写入坐标
    def write_coord(self):

        with open(f'coord/random{self.n}','w') as file:
            #遍历坐标写入文件
            for i in range(self.n):
                file.write(f'{self.coord[i,0]} {self.coord[i,1]}\r')

    #写入矩阵
    def write_mat(self):
        #写参数
        with open(f'graph_missing_edges/mat/random{self.n}.tsp','w') as file:
            file.write(f'NAME: random{self.n}\r\
TYPE: TSP\r\
DIMENSION: {self.n}\r\
EDGE_WEIGHT_TYPE: EXPLICIT\r\
EDGE_WEIGHT_FORMAT: UPPER_DIAG_ROW\r\
EDGE_WEIGHT_SECTION\r')
            
            #写矩阵,只写上三角
            for i in range(self.n):
                for j in range(self.n):
                    if i <= j:
                        file.write(str(self.mat_missing_edges[i,j])[:-2] + '\r')

            file.write("EOF")

    #写入参数文件
    def write_par(self):
        with open(f'graph_missing_edges/par/random{self.n}.par','w') as file:
            file.write(f'PROBLEM_FILE = graph_missing_edges/mat/random{self.n}.tsp\r\
INITIAL_PERIOD = 1000\r\
MAX_CANDIDATES = 4\r\
MAX_TRIALS = 1000\r\
MOVE_TYPE = 6\r\
PATCHING_C = 6\r\
PATCHING_A = 5\r\
RECOMBINATION = GPX2\r\
RUNS = 1\r\
TOUR_FILE = graph_missing_edges/tour/random{self.n}.txt')

    #LKH
    def LKH(self):
        subprocess.run(['LKH-2.exe',f'73/uncom/random{self.n}.par'])

    #用gurobi最优化
    def gurobi(self,lambda_list = None):

        #创建模型
        model = gp.Model(f"TSP_QUBO_test_{self.n}")


        # 创建二进制变量
        x = {}
        for i in range(self.n):
            for j in range(self.n):
                    x[i, j] = model.addVar(vtype=gp.GRB.BINARY, name=f"x_{i}_{j}")



        # 目标函数（使用QUBO形式）
        obj_expr = 0
        for i in range(self.n):
            for j in range(self.n):
                d_ij = self.mat[i,j]
                for t in range(self.n):     
                    obj_expr += d_ij * x[i, t] * x[j,(t+1)%self.n]

        #城市惩罚系数为一个值
        if lambda_list == None:
            # 直接添加约束到obj，城市约束
            for i in range(self.n):
                obj_expr += self.seg1_lambda * (   (sum(x[i, t] for t in range(self.n)) - 1)**2  )

        #城市惩罚系数为列表
        else:
            # 列表形式，城市约束
            for i in range(self.n):
                obj_expr += self.de_lambda_list[i] * (   (sum(x[i, t] for t in range(self.n)) - 1)**2  )


        # 直接添加约束到obj，时间约束
        for t in range(self.n):
            obj_expr += self.seg1_lambda * ((sum(x[i, t] for i in range(self.n)) - 1)**2 )


        #目标函数最小化
        model.setObjective(obj_expr, gp.GRB.MINIMIZE)

        #设置求解器时间参数 
        model.Params.TimeLimit = 7200

        #设置cutoff
        #model.setParam('Cutoff', 202)

        #设置日志文件名
        log_file = f'log_3/random{self.n}.log' 

        #设置求解器参数，将日志输出到文件
        model.Params.LogFile = log_file

        # 优化
        model.optimize()


        #检查可行性
        #到达时间限制  或者找到最优解（似乎可以不用这个条件）
        #if model.status == gp.GRB.TIME_LIMIT or model.status == gp.GRB.OPTIMAL:

        #记录打破的制约的个数
        un_city = 0
        un_time = 0

        #检查城市约束是否满足
        for i in range(self.n):
            if sum(x[i,t].x for t in range(self.n)) != 1:
                un_city += 1
            

        #检查时间约束是否满足
        for t in range(self.n):
            if sum(x[i,t].x for i in range(self.n)) != 1:
                un_time += 1

        #记录
        with open(f'log_3/random{self.n}.log','a') as file:
            file.write(f'\rcity broken:{un_city},time broken:{un_time}\r')

            #记录当前的变量矩阵
            for i in range(self.n):
                x_value = [int(x[i,t].x) for t in range(self.n) ]
                file.write('\r'+str(x_value))

    #用gurobi解TSP
    def gurobi_LKH(self):
         #创建模型
        model = gp.Model(f"TSP_QUBO_test_{self.n}")


        # 创建二进制变量
        x = {}
        for i in range(self.n):
            for j in range(self.n):
                    x[i, j] = model.addVar(vtype=gp.GRB.BINARY, name=f"x_{i}_{j}")



        # 目标函数（使用QUBO形式）
        obj_expr = 0
        for i in range(self.n):
            for j in range(self.n):
                d_ij = self.mat[i,j]
                for t in range(self.n):     
                    obj_expr += d_ij * x[i, t] * x[j,(t+1)%self.n]
        pass

        # 添加约束，城市约束
        city_constraints = {}
        for i in range(self.n):
            city_constraints[i] = model.addConstr(
            gp.quicksum(x[i, t] for t in range(self.n)) == 1,
            name=f"city_constraint_{i}"
        )

        # 添加约束，时间约束
        time_constraints = {}
        for t in range(self.n):
            time_constraints[t] = model.addConstr(
            gp.quicksum(x[i, t] for i in range(self.n)) == 1,
            name=f"time_constraint_{t}"
        )
            
        #目标函数最小化
        model.setObjective(obj_expr, gp.GRB.MINIMIZE)

        #设置求解器时间参数 
        model.Params.TimeLimit = 100

        #设置日志文件名
        log_file = f'log/random{self.n}.log' 

        #设置求解器参数，将日志输出到文件
        model.Params.LogFile = log_file

        # 优化
        model.optimize()


        if model.status == gp.GRB.OPTIMAL:
            print('最短路径长度:', model.objVal)
            print('最短路径:')
            tour = []
            
            for j in range(self.n):
                for i in range(self.n):
                    if x[i,j].x == 1:
                        tour.append(i+1)
            print(tour)

    #如果不是子图画出没有包含的边
    def draw_not_subgraph(self):
        result = is_subgraph(self.graph_optimal_tour,self.graph_seg1_nei2)
        G = self.graph_optimal_tour
        #如果不是子图
        if result[0] == False:

            #格式化需要特别画出的边
            edge_list = list(map(lambda x: tuple(x), result[1]))

            nx.draw(G,self.graph_pos, with_labels=True, node_size=300, node_color='skyblue')
            nx.draw_networkx_edges(G,self.graph_pos,edge_list,edge_color='r',width=3)
            plt.show()

        else:
            return None


if __name__ == '__main__':
    #dic = read_json()
    # for i in range(5,6):
    #     ins = instance(i)

    creat_dump_data_dic()
    

        #print(dic[f'{i}']['add_is_subgraph'])






