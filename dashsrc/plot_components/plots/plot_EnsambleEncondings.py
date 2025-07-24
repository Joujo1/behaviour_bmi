import plotly.graph_objects as go

import pandas as pd
import numpy as np
from dash import dcc, html
from plotly.subplots import make_subplots

def render_plot(encoding_data):
    print(encoding_data)

    # Define color mapping for behavioral variables
    color_mapping = {
        # Velocity group (warm colors)
        'forward_vel': '#FFD700',      # Gold yellow
        'sideway_vel': '#FF4444',      # Bright red
        'sideway_vel_abs': "#FF6E6E",  # Light red
        'rotation_vel': '#FF8C00',     # Dark orange
        'rotation_vel_abs': "#FFAF4E",  # Light orange
        
        # Current acceleration group (cool colors)
        'forward_acc': "#2587C8",      # Strong blue
        'forward_acc_abs': "#4E80A0",  # Light blue
        'forward_acc_positive_only': '#1ABC9C',  # Turquoise
        'forward_acc_negative_only': "#125F50",  # Light turquoise
        
        # Future acceleration group (purple/violet shades)
        'forward_acc_in1sec': "#A01ADA",       # Strong purple
        'forward_acc_abs_in1sec': "#AE60CD",   # Light purple
        'forward_acc_positive_only_in1sec': "#FF00B3",  # Violet
        'forward_acc_negative_only_in1sec': "#650052",  # Light violet
    }
    
    behavior_variables = encoding_data['behavior_variable'].unique() 
    ensembles = sorted(encoding_data['ensemble'].unique())
    # Create subplot pairs for each ensemble
    n_ensembles = len(ensembles)
    
    # Calculate vertical spacing based on number of ensembles
    # v_space = min(0.015, 1.0 / (2*n_ensembles - 1))  # Ensure spacing doesn't exceed maximum
    # print(v_space)
    # v_space_between_pairs = min(0.03, 2.0 / (2*n_ensembles - 1))  # Larger spacing between pairs
    # print(v_space_between_pairs)

    # Create custom row heights: slightly smaller for pairs, larger gaps between pairs
    row_heights = []
    for i in range(n_ensembles):
        # Add pair of subplot heights with spacer
        row_heights.extend([.35/n_ensembles, .5/n_ensembles, 0.5/n_ensembles])  # Last one is spacer row
    
    # # Create titles only for actual plots (not spacers)
    # subplot_titles = []
    # for ens in ensembles:
    #     subplot_titles.extend([f'Ensemble {ens} - Baseline', f'Ensemble {ens} - Behavior Correlations', None])
    
    fig = make_subplots(
        rows=3*n_ensembles, cols=1,
        shared_xaxes=True,
        vertical_spacing=.001,
        # subplot_titles=subplot_titles,
        row_heights=row_heights
    )

    # Add gaps between ensemble pairs
    fig.update_layout(height=250*n_ensembles)  # Scale height with number of ensembles, min 300px
    
    for i, ensemble in enumerate(ensembles):
        ensemble_data = encoding_data[encoding_data['ensemble'] == ensemble]
        base_row = 3*i + 1  # First row of the trio (plot, plot, spacer)
        
        # Plot baseline activation
        # shift timestamps to start from previous session, for one long timeline
        session_t_offset = ensemble_data.groupby('session_id').apply(lambda x: x.iloc[-1]).ephys_timestamp
        s_ids = session_t_offset.index
        session_t_offset = [0, *session_t_offset.iloc[:-1].tolist()]
        session_t_offset = np.cumsum(pd.Series(session_t_offset, index=s_ids))
        ensemble_data.loc[:, 'ephys_timestamp'] = ensemble_data.loc[:, ['session_id', 'ephys_timestamp']].apply(
            lambda x: x['ephys_timestamp'] + session_t_offset[x['session_id']],
            axis=1
        )
        
        for s_id in ensemble_data['session_id'].unique():
            session_data = ensemble_data[ensemble_data['session_id'] == s_id]
            
            
            print(session_data)
            
            # Plot baseline activity
            first_var_data = session_data[session_data['behavior_variable'] == 'forward_vel']
            
            x = first_var_data['ephys_timestamp'].values
            baseline_data = first_var_data.avg_activation.values
        
        # first_var_data = ensemble_data[ensemble_data['behavior_variable'] == 'forward_vel']

        # x = first_var_data['ephys_timestamp'].values#[:-3]
        # baseline_data = first_var_data.avg_activation.values#[:-3]
        # baseline_data[np.abs(baseline_data) > 1.3] = np.nan  # Filter out extreme values
        
            fig.add_trace(
                go.Scatter(
                    x=x, 
                    y=baseline_data, 
                    mode='lines', 
                    name='Baseline Activity',
                    legendgroup='baseline',  # Add legendgroup for baseline
                    line=dict(color='black'),
                    showlegend=bool(i==0 and s_id == session_data['session_id'].unique()[0])  # Show legend only once, convert to Python bool
                ),
                row=base_row, col=1
            )
            fig.add_annotation(
                # xref='x domain', yref='y domain',
                x=x[0], y=baseline_data.max(),  # Centered above the plot
                text=f"S{s_id:02}",
                showarrow=False,
                font=dict(size=12),
                row=base_row, col=1  # Place annotation in the correct row
            )
            
            # Plot behavioral correlations
            for behavior_variable in behavior_variables:
                ensemble_behavior_data = session_data[session_data['behavior_variable'] == behavior_variable]
                # y = ensemble_behavior_data.r2.values[:-3]  # or p_val_highlow_activation
                y = ensemble_behavior_data.p_val_highlow_activation.values#[:-3]
                
                # smooth the data
                y = pd.Series(y).rolling(window=8, min_periods=2).median().values

                fig.add_trace(
                    go.Scatter(
                        x=x, 
                        y=y, 
                        mode='lines', 
                        name=behavior_variable,  # Name must match legendgroup
                        legendgroup=behavior_variable,  # Group traces by behavior variable
                        line=dict(color=color_mapping.get(behavior_variable, '#808080')),  # Use defined color or gray if not found
                        showlegend=bool(i==0 and s_id == session_data['session_id'].unique()[0]),  # Show legend only once, convert to Python bool
                        legendgrouptitle_text=behavior_variable if bool(i==0 and s_id == session_data['session_id'].unique()[0]) else None,
                    ),
                    row=base_row+1, col=1
                )
                
            # spacer plot (empty, invisible)
            fig.add_trace(
                go.Scatter(
                    x=[x[0], x[-1]], 
                    y=[0, 0],  # Just two points for minimal data
                    mode='lines',
                    line=dict(width=0),  # Invisible line
                    showlegend=False,
                    hoverinfo='skip'  # Disable hover information
                ),
                row=base_row+2, col=1
            )
            
            # Update axes for this ensemble pair
            # fig.update_yaxes(title_text='Activity', row=base_row, col=1)
            fig.update_yaxes(title_text=ensemble, row=base_row+1, col=1, range=[0, .1])

            if i == n_ensembles-1:  # Last ensemble
                fig.update_xaxes(title_text='Time (s)', row=base_row+1, col=1)
                
            # Set x-range consistently for all subplots
            # fig.update_xaxes(range=[x.min(), x.max()], row=base_row, col=1)
            # fig.update_xaxes(range=[x.min(), x.max()], row=base_row+1, col=1)
            
        
    # Update layout
    fig.update_layout(
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255, 255, 255, 0.8)",  # Semi-transparent white background
        ),
        margin=dict(r=150, t=50, l=50, b=50),  # Adjust margins
        font=dict(size=10),  # Smaller font size for better fit
        plot_bgcolor='white',
        paper_bgcolor='white',
        # width=3000
    )
    
    
    # Update all subplot properties for better visibility
    for i in range(1, 3*n_ensembles + 1):
        # For actual plots (not spacers)
        if i % 3 != 0:  # If not a spacer row
            fig.update_yaxes(gridcolor='lightgrey', showgrid=True, row=i, col=1)
            fig.update_xaxes(gridcolor='lightgrey', showgrid=True, row=i, col=1)
        else:  # For spacer rows
            fig.update_yaxes(visible=False, row=i, col=1)
            fig.update_xaxes(visible=False, row=i, col=1)
        
    return fig