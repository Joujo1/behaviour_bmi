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
    

    
    print(avg_frate_matrix)
    # rowwise zscore normalization
    # avg_frate_matrix.loc[:] = zscore(avg_frate_matrix, axis=1, nan_policy='omit')
    # rowwise max normalization
    avg_frate_matrix.loc[:] /= avg_frate_matrix.max(axis=1, skipna=True).values[:, np.newaxis]
    print(avg_frate_matrix)
    
    
    
    # Perform hierarchical clustering
    from scipy.cluster.hierarchy import linkage, leaves_list
    linkage_matrix = linkage(avg_frate_matrix, method='ward')  # Using Ward's method
    ordered_indices = leaves_list(linkage_matrix)  # Get the order of rows
    # Reorder the rows of spks based on clustering
    avg_frate_matrix = avg_frate_matrix.iloc[ordered_indices]
    
    avg_frate_matrix = avg_frate_matrix.reset_index()
    avg_frate_matrix.drop("cluster_id", axis=1, inplace=True)
    avg_frate_matrix = avg_frate_matrix.droplevel(0, axis=1)  # Drop the first level of the MultiIndex columns
    print(avg_frate_matrix)
    
    # Create heatmap figure

    fig = go.Figure(
        data=go.Heatmap(
            z=avg_frate_matrix.values,
            x=avg_frate_matrix.columns,
            y=avg_frate_matrix.index,
            colorscale=[
                [0, '#ffffff'], [.1, '#eaeaea'], [.2, '#d9d9d9'],
                [.3, '#c9c9c9'], [.4, '#b7b7b7'],
                [.5, '#9b9b9b'], [.6, '#818181'], [.7, '#716468'],
                [.8, '#70525c'], [.9, '#7d3d54'], [1, '#752541']
            ],
            colorbar=dict(title='Avg Firing Rate (Hz, normalized)'),
            zmin=0,
            zmax=1,
            # colorscale=px.colors.diverging.RdBu_r,
            # colorbar=dict(title='Avg Firing Rate (Z-score)'),
            # zmin=-3,
            # zmax=3,
        )
    )
    fig.update_layout(
        xaxis_title="Session",
        yaxis_title="Cluster",
        title="Average Firing Rate per Cluster/Session",
        template="plotly_white"
    )
    return fig