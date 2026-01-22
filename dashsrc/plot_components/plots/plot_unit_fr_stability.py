import plotly.graph_objects as go
import pandas as pd
import numpy as np
from scipy.stats import zscore
from scipy.cluster.hierarchy import linkage, leaves_list

def render_plot_heatmap(spike_metadata, cluster=False):
    """
    Render a heatmap of average firing rates for each cluster across sessions.
    
    Args:
        spike_metadata (DataFrame): Contains spike metadata including cluster_id, 
                                   session_spike_count and session_nsamples
    
    Returns:
        plotly.graph_objects.Figure: Heatmap of firing rates
    """
    # Compute average firing rate for each (cluster, session)
    sess_spk_cnt = spike_metadata['session_spike_count']
    sess_seconds = spike_metadata['session_nsamples'] / 20_000
    
    # Create and format DataFrame
    avg_frate = (sess_spk_cnt / sess_seconds).to_frame(name='avg_frate').droplevel((0, 1, 3))
    avg_frate['cluster_id'] = spike_metadata['cluster_id'].values
    avg_frate = avg_frate.set_index('cluster_id', append=True)
    print(avg_frate)
    # Convert to matrix format
    avg_frate_matrix = avg_frate.unstack(level=0)
    avg_frate_matrix.columns = avg_frate_matrix.columns.droplevel(0)
    
    # Define firing rate bins
    bins = (0, 0.00001, 0.1, 1, 2, 4, 8, 16, 32, 64)
    
# Bin the firing rates for clustering
    avg_frate_matrix_bin_id = np.zeros_like(avg_frate_matrix, dtype=int)
    for i in range(len(bins) - 1):
        from_val, to_val = bins[i], bins[i+1]
        mask = (avg_frate_matrix > from_val) & (avg_frate_matrix <= to_val)
        avg_frate_matrix_bin_id[mask] = i
    
    if cluster:
        # Hierarchical clustering
        linkage_matrix = linkage(
            avg_frate_matrix_bin_id, 
            metric='cityblock', 
            method='complete', 
            optimal_ordering=True
        )
        ordered_indices = leaves_list(linkage_matrix)
        
        # Reorder rows based on clustering results
        avg_frate_matrix = avg_frate_matrix.iloc[ordered_indices]
        
    
    # clip to < 1Hz, > 1Hz    
    # avg_frate_matrix.loc[:] = (avg_frate_matrix > 1).astype(float).values
    
    # Create color scale for the heatmap
    maxval = 32
    eps = .000001
    fr_cscale = [
        [0, '#ffffff'], 
        [(0+eps)/maxval, "#e8e8e8"], [.1/maxval, "#e8e8e8"], 
        [(.1+eps)/maxval, "#8C6565"], [1/maxval, "#8C6565"], 
        [(1+eps)/maxval, "#8C6565"], [2/maxval, "#8C6565"],
        [(2+eps)/maxval, "#963F3F"], [4/maxval, "#963F3F"],
        [(4+eps)/maxval, "#A73131"], [8/maxval, "#A73131"],
        [(8+eps)/maxval, "#D1552C"], [16/maxval, "#D1552C"],
        [(16+eps)/maxval, "#D1922C"], [32/maxval, "#D1922C"],
    ]
    

    # Create custom colorbar tick values and text
    colorbar_tickvals = [0, 0.05, 0.5, 1.5, 3, 6, 12, 24]
    colorbar_ticktext = ["Not detected", "<0.1 Hz", "<1 Hz", "<2 Hz", "<4 Hz", "<8 Hz", "<16 Hz", "<32 Hz"]
    
    # Create heatmap figure
    fig = go.Figure(
        data=go.Heatmap(
            z=avg_frate_matrix.values,
            x=np.arange(avg_frate_matrix.columns.size),
            y=np.arange(avg_frate_matrix.index.size),
            colorscale=fr_cscale,
            colorbar=dict(
                title='Avg Firing Rate',
                tickvals=colorbar_tickvals,
                ticktext=colorbar_ticktext,
                tickmode='array',
                len=0.75,  # Make colorbar slightly shorter to fit all labels
                thickness=20,  # Make colorbar wider for better text readability
                tickfont=dict(size=10)
            ),
            zmin=0,
            zmax=maxval,
        )
    )
    
    # Update layout with reduced dimensions
    fig.update_layout(
        width=800,  # Updated width
        height=800, # Updated height
        xaxis_title="Session ID",
        yaxis_title="Single Unit ID",
        title="Average Firing Rate per Neuron/Session",
        template="plotly_white",
        yaxis=dict(
            tickmode='array',
            tickvals=np.arange(avg_frate_matrix.index.size),
            ticktext=avg_frate_matrix.index.tolist(),
            tickfont=dict(size=8, color='black'),  # Changed from font_dict to tickfont
        ),
        xaxis=dict(
            tickmode='array',
            tickvals=np.arange(avg_frate_matrix.columns.size),
            ticktext=avg_frate_matrix.columns.tolist(),
            tickfont=dict(size=10, color='black'),  # Changed from font_dict to tickfont
        )
    )
    return fig


def render_plot_lineplot(data):
    """
    Render a line plot of average firing rates for each unit across sessions,
    including the mean firing rate across all units.
    
    Args:
        data (DataFrame): Either:
            - spike_metadata with columns ['session_spike_count', 'session_nsamples', 'cluster_id']
            - firing rate data with columns like 'Unit0001', 'Unit0002', etc.
    
    Returns:
        plotly.graph_objects.Figure: Line plot of firing rates over sessions
    """
    # Detect input type and process accordingly
    if 'session_spike_count' in data.columns:
        # Original spike_metadata format
        sess_spk_cnt = data['session_spike_count']
        sess_seconds = data['session_nsamples'] / 20_000
        
        # Create and format DataFrame
        avg_frate = (sess_spk_cnt / sess_seconds).to_frame(name='avg_frate').droplevel((0, 1, 3))
        avg_frate['cluster_id'] = data['cluster_id'].values
        avg_frate = avg_frate.set_index('cluster_id', append=True)
        
        # Convert to matrix format for easier processing
        avg_frate_matrix = avg_frate.unstack(level=1)  # Unstack cluster_id instead
        avg_frate_matrix.columns = avg_frate_matrix.columns.droplevel(0)
    else:
        # Firing rate data format (Unit0001, Unit0002, etc.)
        # Select only Unit columns
        unit_cols = [col for col in data.columns if col.startswith('Unit')]
        fr_data = data[unit_cols].copy()
        
        # Group by session_id and compute mean firing rate per session
        session_idx = fr_data.index.get_level_values('session_id')
        avg_frate_matrix = fr_data.groupby(session_idx).mean()
        
        # Convert column names from Unit0001 to integers
        avg_frate_matrix.columns = [int(col.replace('Unit', '')) for col in avg_frate_matrix.columns]
    
    # Create figure
    fig = go.Figure()
    
    # Plot each unit as a line
    for cluster_id in avg_frate_matrix.columns:
        fig.add_trace(go.Scatter(
            x=avg_frate_matrix.index.values,
            y=avg_frate_matrix[cluster_id].values,
            mode='lines+markers',
            name=f'Unit {cluster_id}',
            line=dict(width=1),
            marker=dict(size=4),
            opacity=0.5,
            showlegend=True
        ))
    
    # Calculate and plot mean across all units
    mean_frate = avg_frate_matrix.mean(axis=1)
    fig.add_trace(go.Scatter(
        x=avg_frate_matrix.index.values,
        y=mean_frate.values,
        mode='lines+markers',
        name='Mean',
        line=dict(width=3, color='black', dash='dash'),
        marker=dict(size=8, color='black'),
        opacity=1.0,
        showlegend=True
    ))
    
    # Update layout
    fig.update_layout(
        width=1000,
        height=600,
        xaxis_title="Session ID",
        yaxis_title="Average Firing Rate (Hz)",
        title="Firing Rate Stability Across Sessions",
        template="plotly_white",
        xaxis=dict(
            tickmode='array',
            tickvals=avg_frate_matrix.index.tolist(),
            ticktext=avg_frate_matrix.index.tolist(),
            tickfont=dict(size=10, color='black'),
        ),
        yaxis=dict(
            tickfont=dict(size=10, color='black'),
        ),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            font=dict(size=8)
        )
    )
    
    return fig


def render_plot_amplitude(spike_metadata, sess_vpp, highlight_cluster):
    # Compute average firing rate for each (cluster, session)
    sess_spk_cnt = spike_metadata['session_spike_count']
    sess_seconds = spike_metadata['session_nsamples'] / 20_000
    # sess_vpp = spike_metadata['unit_Vpp']   
    sess_snr = spike_metadata['unit_snr']
    
    # Create and format DataFrame
    sess_spiking = (sess_spk_cnt / sess_seconds).to_frame(name='avg_frate').droplevel((0, 1, 3))
    sess_spiking['cluster_id'] = spike_metadata['cluster_id'].values
    sess_spiking['unit_snr'] = sess_snr.values
    sess_spiking = sess_spiking.set_index('cluster_id', append=True)
    
    print(sess_vpp)
    sess_vpp = sess_vpp.reindex(sess_spiking.index)
    print(sess_vpp)
    sess_spiking['unit_Vpp'] = sess_vpp.values*6.3
    

    print(sess_spiking)
    fig = go.Figure()
    
    for clust_id in sess_spiking.index.unique('cluster_id'):
        clust_data = sess_spiking.xs(clust_id, level='cluster_id')
        
        # Add average firing rate trace
        fig.add_trace(go.Scatter(
            x=clust_data.index.get_level_values('session_id'),
            y=clust_data['unit_Vpp'],
            mode='lines',
            showlegend=False,
            opacity=0.3,
            line=dict(width=2, color='darkgrey'),
        ))
        
    fig.update_layout(
        width=800,  # Updated width
        height=400, # Updated height
        xaxis_title="Session ID",
        yaxis_title="Average Spike Amplitude (uV)",
        title="Amplitude stability per Neuron over Sessions",
        template="plotly_white",
        yaxis=dict(
            range=[0, -250],
            tickfont=dict(size=8, color='black'),  # Changed from font_dict to tickfont
        ),
        xaxis=dict(
            tickmode='array',
            tickvals=clust_data.index.unique('session_id').tolist(),
            # Use the session IDs as tick labels
            ticktext=clust_data.index.unique('session_id').tolist(),
            tickfont=dict(size=10, color='black'),  # Changed from font_dict to tickfont
        )
    )
    
    maxval = 32
    eps = .000001
    fr_cscale = [
        [0, '#ffffff'], 
        [(0+eps)/maxval, "#e8e8e8"], [.1/maxval, "#e8e8e8"], 
        [(.1+eps)/maxval, "#d5d5d5"], [1/maxval, "#d5d5d5"], 
        [(1+eps)/maxval, "#8C6565"], [2/maxval, "#8C6565"],
        [(2+eps)/maxval, "#963F3F"], [4/maxval, "#963F3F"],
        [(4+eps)/maxval, "#A73131"], [8/maxval, "#A73131"],
        [(8+eps)/maxval, "#D1552C"], [16/maxval, "#D1552C"],
        [(16+eps)/maxval, "#D1922C"], [32/maxval, "#D1922C"],
    ]
    
    if highlight_cluster is not None:
        highlight_data = sess_spiking.xs(highlight_cluster, level='cluster_id')
        
        fig.add_trace(go.Scatter(
            x=highlight_data.index.get_level_values('session_id'),
            y=highlight_data['unit_Vpp'],
            mode='markers+lines',
            name=f'Neuron {highlight_cluster:02}',
            line=dict(width=2, color='black'),
            marker=dict(
                size=8, 
                color=highlight_data['avg_frate'],
                symbol='circle', 
                colorscale=fr_cscale,
                cmin=0,
                cmax=maxval,  # Use the same scale as in heatmap
                colorbar=dict(
                    title='Avg Firing Rate',
                    tickvals=[0, 1, 3, 6, 12, 16, 24, 32],  # Actual values matching your scale
                    ticktext=["Not detected", "<0.1 Hz", "<1 Hz", "1-2 Hz", "2-4 Hz", "4-8 Hz", "8-16 Hz", ">16 Hz"],
                    tickmode='array',
                    len=0.75,
                    thickness=20,
                    tickfont=dict(size=8)
                )
            ),
        ))
            
        
        
    return fig
