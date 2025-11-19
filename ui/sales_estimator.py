import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from services.keepa_service import KeepaProduct

def render_sales_estimator_tab(api_key):
    st.header("Sales Estimator")
    st.write("Enter ASINs to estimate sales and view historical data.")

    # ASIN input for individual analysis
    col1, col2 = st.columns([3, 1])
    with col1:
        asin_input = st.text_input("Enter ASIN for individual analysis (e.g., B07XXXXXXX):")
    with col2:
        domain_selection = st.selectbox("Select Amazon Domain", ["US", "DE", "ES", "FR", "GB", "IN", "IT", "JP", "MX", "AE", "AU", "BR", "CA", "CN"], index=0)

    if st.button("Analyze Single ASIN", type="primary"):
        if asin_input:
            with st.status(f"Fetching data for {asin_input}...", expanded=True) as status:
                product = KeepaProduct(api_key, asin=asin_input, domain=domain_selection)
                product.query()
                
                if product.exists:
                    status.write("Data found. Processing history...")
                    product.get_last_days(days=360) # Get last 360 days of data
                    status.update(label="Analysis Complete", state="complete", expanded=False)
                    
                    st.subheader(f"Analysis for {product.title} ({product.asin})")
                    
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        if product.image:
                            st.image(product.image, width=150)
                    with c2:
                        st.write(f"**Brand:** {product.brand}")
                        st.write(f"**Average Monthly Sales (last 30 days):** {product.avg_sales:,.0f}")
                        st.write(f"**Average Price (last 30 days):** ${product.avg_price:,.2f}")
                        st.write(f"**Total Sales Value (last 30 days):** ${(product.avg_sales * product.avg_price):,.0f}")

                    # Plotting sales and price history
                    if product.pivot is not None and not product.pivot.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=product.pivot.index, y=product.pivot['sales max'], mode='lines', name='Max Sales'))
                        fig.add_trace(go.Scatter(x=product.pivot.index, y=product.pivot['sales min'], mode='lines', name='Min Sales'))
                        fig.add_trace(go.Scatter(x=product.pivot.index, y=product.pivot['final price'], mode='lines', name='Average Price', yaxis='y2'))

                        fig.update_layout(
                            title=f'Sales and Price History for {product.title}',
                            xaxis_title='Date',
                            yaxis_title='Estimated Sales',
                            yaxis2=dict(title='Price ($)', overlaying='y', side='right'),
                            legend=dict(x=0.01, y=0.99),
                            hovermode="x unified"
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("No historical sales data available for plotting.")

                    with st.expander("Show Detailed Daily Sales History"):
                        sales_history_df = product.get_sales_history_by_date()
                        if not sales_history_df.empty:
                            st.dataframe(sales_history_df, use_container_width=True)
                        else:
                            st.write("Daily sales history not available.")
                else:
                    status.update(label="Error", state="error")
                    st.error(f"Could not find data for ASIN: {asin_input}. Please check the ASIN and domain.")
        else:
            st.warning("Please enter an ASIN to analyze.")

    st.divider()

    # Bulk ASIN analysis
    st.subheader("Bulk ASIN Analysis")
    with st.expander("Bulk Analysis Settings", expanded=True):
        bulk_asins_input = st.text_area("Enter ASINs (one per line):", height=150)
        bulk_domain_selection = st.selectbox("Select Amazon Domain for Bulk Analysis", ["US", "DE", "ES", "FR", "GB", "IN", "IT", "JP", "MX", "AE", "AU", "BR", "CA", "CN"], index=0, key="bulk_domain")

    if st.button("Analyze Bulk ASINs"):
        if bulk_asins_input:
            asins_list = [a.strip() for a in bulk_asins_input.split('\n') if a.strip()]
            if asins_list:
                all_products_data = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, asin in enumerate(asins_list):
                    status_text.text(f"Processing {i+1}/{len(asins_list)}: {asin}")
                    progress_bar.progress((i + 1) / len(asins_list))
                    
                    product = KeepaProduct(api_key, asin=asin, domain=bulk_domain_selection)
                    product.query()
                    if product.exists:
                        product.get_last_days(days=30) # Get last 30 days for bulk summary
                        all_products_data.append({
                            "ASIN": product.asin,
                            "Title": product.title,
                            "Brand": product.brand,
                            "Avg Monthly Sales": f"{product.avg_sales:,.0f}",
                            "Avg Price": f"${product.avg_price:,.2f}",
                            "Total Sales Value": f"${(product.avg_sales * product.avg_price):,.0f}",
                            "Product Link": f"https://www.amazon.com/dp/{product.asin}",
                            "Image": product.image
                        })
                
                progress_bar.empty()
                status_text.empty()

                if all_products_data:
                    df_bulk = pd.DataFrame(all_products_data)
                    st.success("Bulk Analysis Complete!")
                    st.dataframe(
                        df_bulk,
                        column_config={
                            "Image": st.column_config.ImageColumn("Image"),
                            "Product Link": st.column_config.LinkColumn("Link")
                        },
                        use_container_width=True
                    )
                    st.download_button(
                        label="Download CSV",
                        data=df_bulk.to_csv(index=False).encode('utf-8'),
                        file_name="bulk_asin_analysis.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning("No data found for the provided ASINs.")
            else:
                st.warning("Please enter valid ASINs for bulk analysis.")
        else:
            st.warning("Please enter ASINs for bulk analysis.")
