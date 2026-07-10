from scrapers.factory import ScraperFactory
import asyncio

class TrackingService:
    @staticmethod
    async def track_shipments(shipments, task_id, progress_callback):
        total = len(shipments)
        for i, shipment in enumerate(shipments):
            awb = shipment["tracking_number"]
            courier = shipment["courier"]
            
            # Notify progress
            await progress_callback(
                progress=int(((i) / total) * 100),
                current_action=f"Tracking {awb} via {courier}...",
                log_message=f"Starting scraping for {courier} AWB {awb}...",
                log_level="info"
            )
            
            scraper = ScraperFactory.get_scraper(courier)
            if scraper:
                try:
                    result = await scraper.track(awb)
                    shipment["status"] = result["status"]
                    shipment["last_location"] = result["last_location"]
                    shipment["timestamp"] = result["timestamp"]
                    
                    log_level = "success" if "delivered" in result["status"].lower() else "info"
                    if "error" in result["status"].lower() or "invalid" in result["status"].lower():
                        log_level = "error"
                        
                    await progress_callback(
                        progress=int(((i + 1) / total) * 100),
                        current_action=f"Finished tracking {awb}",
                        log_message=f"Successfully scraped {courier} AWB {awb}. Status: {result['status']}",
                        log_level=log_level
                    )
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    print(f"--- SCRAPER EXCEPTION TRACEBACK ---\n{tb}------------------------------------")
                    error_msg = str(e) or type(e).__name__
                    shipment["status"] = "Scrape Failed"
                    shipment["last_location"] = error_msg
                    await progress_callback(
                        progress=int(((i + 1) / total) * 100),
                        current_action=f"Error tracking {awb}",
                        log_message=f"Error scraping {courier} AWB {awb}: {error_msg}",
                        log_level="error"
                    )
            else:
                # Fallback mock/warning if scraper not implemented yet
                shipment["status"] = "Scraper Not Implemented"
                shipment["last_location"] = "Service pending integration"
                await progress_callback(
                    progress=int(((i + 1) / total) * 100),
                    current_action=f"Skipping {awb}",
                    log_message=f"Scraper for courier '{courier}' is not implemented yet. Skipping AWB {awb}.",
                    log_level="warning"
                )
            
            # small delay between calls (longer for bluedart to prevent rate-limiting)
            delay = 2.0 if courier.lower() == "bluedart" else 0.5
            await asyncio.sleep(delay)
            
        # Final update
        await progress_callback(
            progress=100,
            current_action="Scraping run completed",
            log_message="All tracking numbers processed.",
            log_level="success"
        )
