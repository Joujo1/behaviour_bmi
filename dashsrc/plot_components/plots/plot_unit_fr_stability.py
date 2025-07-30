import plotly.graph_objects as go
import json
import re
from scipy.stats import zscore
        
import pandas as pd
import numpy as np
from dash import dcc, html
from plotly.subplots import make_subplots
import plotly.express as px

# def render_plot(spike_metadata):
#     cluster_id = spike_metadata['cluster_id']
#     sess_spk_cnt = spike_metadata['session_spike_count']
#     sess_seconds = spike_metadata['session_nsamples']/20_000
#     normed_avg_frate = (sess_spk_cnt /sess_seconds).to_frame().rename(columns={0: 'avg_frate'})
        
#     normed_fr_cscale = [[0,'#ffffff'], [.1,'#eaeaea'], [.2,'#d9d9d9'], 
#                         [.3,'#c9c9c9'], [.4,'#b7b7b7',], 
#                         [.5,'#9b9b9b'], [.6,'#818181'], [.7,'#716468'], 
#                         [.8,'#70525c'], [.9,'#7d3d54'], [1,'#752541']]
    
#     fig = make_subplots()
    
#     print(cluster_id)
#     print(sess_spk_cnt)
#     print(sess_seconds)
#     print(normed_avg_frate)







def render_plot(spike_metadata):
    # Compute average firing rate for each (cluster, session)
    sess_spk_cnt = spike_metadata['session_spike_count']
    sess_seconds = spike_metadata['session_nsamples'] / 20_000
    avg_frate = (sess_spk_cnt / sess_seconds).to_frame(name='avg_frate').droplevel((0,1,3))
    avg_frate['cluster_id'] = spike_metadata['cluster_id'].values
    # print(spike_metadata['cluster_id'])
    print(avg_frate)
    
    avg_frate = avg_frate.set_index('cluster_id', append=True)
    print(avg_frate)
    avg_frate_matrix = avg_frate.unstack(level=0)  # Unstack to get cluster_id as columns
    avg_frate_matrix.columns = avg_frate_matrix.columns.droplevel(0)  # Drop the first level of the MultiIndex columns
    
    # log the average firing rate matrix
    # avg_frate_matrix = np.log1p(avg_frate_matrix)

    

    print(avg_frate_matrix)
    # rowwise zscore normalization
    # avg_frate_matrix.loc[:] = zscore(avg_frate_matrix, axis=1, nan_policy='omit')
    
    # rowwise max normalization
    # avg_frate_matrix.loc[:] /= avg_frate_matrix.max(axis=1, skipna=True).values[:, np.newaxis]
    # print(avg_frate_matrix)
    
    # print(avg_frate_matrix)
    bins = (0, 0.00001, 0.1, 1, 2, 4, 8, 16, 32, 64)
    # binned = pd.cut(avg_frate_matrix.values.flatten(), bins=bins, include_lowest=True)
    # shape = avg_frate_matrix.shape

    avg_frate_matrix_binned = np.zeros_like(avg_frate_matrix)
    avg_frate_matrix_bin_id = np.zeros_like(avg_frate_matrix, dtype=int)
    for i in range(len(bins)-1):
        from_val = bins[i]
        to_val = bins[i+1]
        avg_frate_matrix_binned[(avg_frate_matrix > from_val) & (avg_frate_matrix <= to_val)] = from_val
        avg_frate_matrix_bin_id[(avg_frate_matrix > from_val) & (avg_frate_matrix <= to_val)] = i
    
    print(avg_frate_matrix_bin_id)
    avg_frate_matrix_bin_id = np.diff(avg_frate_matrix_bin_id, axis=1)
        

    print(avg_frate_matrix_binned)
    print(avg_frate_matrix_bin_id)
    # Perform hierarchical clustering
    from scipy.cluster.hierarchy import linkage, leaves_list
    # linkage_matrix = linkage(avg_frate_matrix_bin_id, metric='hamming')  # Using Ward's method
    # linkage_matrix = linkage(avg_frate_matrix_bin_id, metric='cityblock')  # Using Ward's method
    linkage_matrix = linkage(avg_frate_matrix_bin_id, metric='cosine')  # Using Ward's method
    ordered_indices = leaves_list(linkage_matrix)  # Get the order of rows
    
    
    # rowwise std
    # ordered_indices = avg_frate_matrix.apply(lambda row: np.diff(row[row!=0]).std(), axis=1).sort_values(ascending=False).index
    # ordered_indices = avg_frate_matrix.apply(lambda row: np.diff(row[row!=0]).std(), axis=1).sort_values(ascending=False).index
    # ordered_indices = avg_frate_matrix.apply(lambda row: np.diff(np.log1p(row)).std(), axis=1).sort_values(ascending=False).index
    
    # print(ordered_indices)
    # print(len(ordered_indices))
    
    # drop indices 
    # l = 51, 15, 17, 2, 5, 3, 13, 4, 9, 18, 14, 11,  44,  47, 48, 10, 34,  27, 19, 55
    

    # l1 =  51, 15, 17, 19, 2, 5,4, 3, 13,  9, 18, 31,64,8,44,11,14
    # l2 = 47, 48, 10, 34
    # l3 =  16,27,  55, 72, 53, 54,41,40, 12, 57, 28, 7, 49, 42, 
    # l4 = 30,32,52,58,6,45,1,73,39,67,77,74
    # l = [*l1, *l2, *l3,*l4]

    # ordered_indices = ordered_indices[~ordered_indices.isin(l)]
    # ordered_indices = [*ordered_indices.tolist(), *reversed(l)]


    # Reorder the rows of spks based on clustering
    avg_frate_matrix = avg_frate_matrix.iloc[ordered_indices]
    # avg_frate_matrix = avg_frate_matrix.loc[ordered_indices]
    
    # avg_frate_matrix = avg_frate_matrix.reset_index()
    # avg_frate_matrix.drop("cluster_id", axis=1, inplace=True)
    # avg_frate_matrix = avg_frate_matrix.droplevel(0, axis=1)  # Drop the first level of the MultiIndex columns
    print(avg_frate_matrix)
    
    # # Create heatmap figure
    maxval = 32
    eps = .000001
    fr_cscale = [[0,'#ffffff'], 
                 [(0+eps)/maxval,"#e2e2e2"], [.1/maxval,"#e2e2e2"], 
                 [(.1+eps)/maxval,"#b1b1b1"], [1/maxval,"#b1b1b1"], 
                 [(1+eps)/maxval,"#8C6565"], [2/maxval,"#8C6565"],
                 [(2+eps)/maxval,"#963F3F"], [4/maxval,"#963F3F"],
                 [(4+eps)/maxval,"#A73131"], [8/maxval,"#A73131"],
                 [(8+eps)/maxval,"#D1552C"], [16/maxval,"#D1552C"],
                 [(16+eps)/maxval,"#D1922C"], [32/maxval,"#D1922C"],
    ]
    fig = go.Figure(
        data=go.Heatmap(
            z=avg_frate_matrix.values,
            x=avg_frate_matrix.columns,
            y=np.arange(avg_frate_matrix.index.size),
            # colorscale=[
            #     [0, '#ffffff'], [.1, '#eaeaea'], [.2, '#d9d9d9'],
            #     [.3, '#c9c9c9'], [.4, '#b7b7b7'],
            #     [.5, '#9b9b9b'], [.6, '#818181'], [.7, '#716468'],
            #     [.8, '#70525c'], [.9, '#7d3d54'], [1, '#752541']
            # ],
            # colorbar=dict(title='Avg Firing Rate (Hz, normalized)'),
            colorbar=dict(title='Avg Firing Rate (Hz)'),
            # zmin=0,
            # zmax=1,
            # colorscale=px.colors.diverging.RdBu_r,
            # colorbar=dict(title='Avg Firing Rate (Z-score)'),
            # zmin=-3,
            # zmax=3,
            colorscale=fr_cscale,
            zmin=0,
            zmax=maxval,
            # zmax=20,
        )
    )
    
    
    fig.update_layout(
        xaxis_title="Session",
        yaxis_title="Cluster",
        title="Average Firing Rate per Cluster/Session",
        template="plotly_white",
        yaxis=dict(
            tickmode='array',
            tickvals=np.arange(avg_frate_matrix.index.size),
            ticktext=avg_frate_matrix.index.tolist(),
        )
    )
    return fig



# 51, 15, 17, 19, 2, 5, 3, 13, 4, 9, 18, 14, 11,  44, 8

# 47, 48, 10, 34

# 27,  55, 53, 57, 28, 7 42, 72